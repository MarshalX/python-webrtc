//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "encoded_frame.h"

#include <cmath>
#include <utility>

#include <api/video/video_frame_metadata.h>
#include <rtc_base/time_utils.h>

#include <pybind11/stl.h>

#include "../utils/buffer.h"
#include "../utils/gil.h"

namespace python_webrtc {

  namespace {

    // libwebrtc times frames with its monotonic clock, Python with the Unix epoch (like the RTP sources)
    constexpr double kUsPerMs = 1000;

    double EpochMs(webrtc::Timestamp time) {
      return (static_cast<double>(time.us()) / kUsPerMs) +
             static_cast<double>(webrtc::TimeUTCMillis() - webrtc::TimeMillis());
    }

    pybind11::list Integers(auto &&values) {
      pybind11::list list;
      for (auto value : values) {
        list.append(value);
      }
      return list;
    }

  } // namespace

  EncodedFrame::EncodedFrame(std::unique_ptr<webrtc::TransformableFrameInterface> frame)
      : _video(dynamic_cast<webrtc::TransformableVideoFrameInterface *>(frame.get()) != nullptr),
        _frame(std::move(frame)) {}

  void EncodedFrame::Init(pybind11::module &m) {
    pybind11::class_<EncodedFrame, std::shared_ptr<EncodedFrame>>(m, "RTCEncodedFrame")
        .def_property_readonly("video", &EncodedFrame::IsVideo)
        .def("getData", &EncodedFrame::GetData)
        .def("getMetadata", &EncodedFrame::GetMetadata);
  }

  pybind11::bytes EncodedFrame::GetData() {
    const std::scoped_lock lock(_mutex);
    if (!_frame) {
      return {};
    }
    auto data = _frame->GetData();
    return Bytes(data.data(), data.size());
  }

  pybind11::dict EncodedFrame::GetMetadata() {
    const std::scoped_lock lock(_mutex);
    pybind11::dict metadata;
    if (!_frame) {
      return metadata;
    }
    const auto &frame = *_frame;
    metadata["synchronizationSource"] = frame.GetSsrc();
    metadata["payloadType"] = frame.GetPayloadType();
    metadata["rtpTimestamp"] = std::visit([](auto timestamp) { return timestamp.value; }, frame.GetRtpTimestampInfo());
    if (auto time = frame.ReceiveTime()) {
      metadata["receiveTime"] = EpochMs(*time);
    }
    if (auto time = frame.CaptureTime()) {
      // a received frame has the capture time of the remote clock, since the epoch already
      const bool received = frame.GetDirection() == webrtc::TransformableFrameInterface::Direction::kReceiver;
      metadata["captureTime"] = received ? static_cast<double>(time->us()) / kUsPerMs : EpochMs(*time);
    }
    if (auto offset = frame.SenderCaptureTimeOffset()) {
      metadata["senderCaptureTimeOffset"] = offset->ms<double>();
    }
    metadata["mimeType"] = frame.GetMimeType();

    if (const auto *video = dynamic_cast<const webrtc::TransformableVideoFrameInterface *>(&frame)) {
      const auto videoMetadata = video->Metadata();
      metadata["contributingSources"] = Integers(videoMetadata.GetCsrcs());
      if (auto frameId = videoMetadata.GetFrameId()) {
        metadata["frameId"] = *frameId;
      }
      if (auto dependencies = videoMetadata.GetDependencies()) {
        metadata["dependencies"] = Integers(*dependencies);
      }
      metadata["width"] = videoMetadata.GetWidth();
      metadata["height"] = videoMetadata.GetHeight();
      metadata["spatialIndex"] = videoMetadata.GetSpatialIndex();
      metadata["temporalIndex"] = videoMetadata.GetTemporalIndex();
      if (auto timestamp = frame.GetPresentationTimestamp()) {
        metadata["timestamp"] = timestamp->us();
      }
      metadata["keyFrame"] = video->IsKeyFrame();
      if (auto rid = video->Rid()) {
        metadata["rid"] = *rid;
      }
    } else if (const auto *audio = dynamic_cast<const webrtc::TransformableAudioFrameInterface *>(&frame)) {
      metadata["contributingSources"] = Integers(audio->GetContributingSources());
      if (auto sequenceNumber = audio->SequenceNumber()) {
        metadata["sequenceNumber"] = *sequenceNumber;
      }
      if (auto level = audio->AudioLevel()) {
        // -dBov, as the linear level of the RTP sources, 127 being silence
        constexpr double base = 10;
        constexpr double dbPerDecade = 20;
        constexpr uint8_t silent = 127;
        metadata["audioLevel"] = *level >= silent ? 0.0 : std::pow(base, -static_cast<double>(*level) / dbPerDecade);
      }
    }
    return metadata;
  }

  std::unique_ptr<webrtc::TransformableFrameInterface> EncodedFrame::Take() {
    const std::scoped_lock lock(_mutex);
    return std::move(_frame);
  }

} // namespace python_webrtc
