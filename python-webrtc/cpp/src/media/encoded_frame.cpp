//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "encoded_frame.h"

#include <cmath>
#include <string>
#include <utility>
#include <variant>
#include <vector>

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

    using Value = std::variant<bool, int64_t, double, std::string, std::vector<int64_t>>;
    using Metadata = std::vector<std::pair<const char *, Value>>;

    std::vector<int64_t> Integers(auto &&values) {
      return {values.begin(), values.end()};
    }

    Metadata MetadataOf(const webrtc::TransformableFrameInterface &frame) {
      Metadata metadata;
      auto set = [&](const char *name, Value value) { metadata.emplace_back(name, std::move(value)); };
      set("synchronizationSource", static_cast<int64_t>(frame.GetSsrc()));
      set("payloadType", static_cast<int64_t>(frame.GetPayloadType()));
      set("rtpTimestamp", static_cast<int64_t>(
                              std::visit([](auto timestamp) { return timestamp.value; }, frame.GetRtpTimestampInfo())));
      if (auto time = frame.ReceiveTime()) {
        set("receiveTime", EpochMs(*time));
      }
      if (auto time = frame.CaptureTime()) {
        // a received frame has the capture time of the remote clock, since the epoch already
        const bool received = frame.GetDirection() == webrtc::TransformableFrameInterface::Direction::kReceiver;
        set("captureTime", received ? static_cast<double>(time->us()) / kUsPerMs : EpochMs(*time));
      }
      if (auto offset = frame.SenderCaptureTimeOffset()) {
        set("senderCaptureTimeOffset", offset->ms<double>());
      }
      set("mimeType", frame.GetMimeType());

      if (const auto *video = dynamic_cast<const webrtc::TransformableVideoFrameInterface *>(&frame)) {
        const auto videoMetadata = video->Metadata();
        set("contributingSources", Integers(videoMetadata.GetCsrcs()));
        if (auto frameId = videoMetadata.GetFrameId()) {
          set("frameId", *frameId);
        }
        if (auto dependencies = videoMetadata.GetDependencies()) {
          set("dependencies", Integers(*dependencies));
        }
        set("width", static_cast<int64_t>(videoMetadata.GetWidth()));
        set("height", static_cast<int64_t>(videoMetadata.GetHeight()));
        set("spatialIndex", static_cast<int64_t>(videoMetadata.GetSpatialIndex()));
        set("temporalIndex", static_cast<int64_t>(videoMetadata.GetTemporalIndex()));
        if (auto timestamp = frame.GetPresentationTimestamp()) {
          set("timestamp", timestamp->us());
        }
        set("keyFrame", video->IsKeyFrame());
        if (auto rid = video->Rid()) {
          set("rid", *rid);
        }
      } else if (const auto *audio = dynamic_cast<const webrtc::TransformableAudioFrameInterface *>(&frame)) {
        set("contributingSources", Integers(audio->GetContributingSources()));
        if (auto sequenceNumber = audio->SequenceNumber()) {
          set("sequenceNumber", static_cast<int64_t>(*sequenceNumber));
        }
        if (auto level = audio->AudioLevel()) {
          // -dBov, as the linear level of the RTP sources, 127 being silence
          constexpr double base = 10;
          constexpr double dbPerDecade = 20;
          constexpr uint8_t silent = 127;
          set("audioLevel", *level >= silent ? 0.0 : std::pow(base, -static_cast<double>(*level) / dbPerDecade));
        }
      }
      return metadata;
    }

  } // namespace

  EncodedFrame::EncodedFrame(std::unique_ptr<webrtc::TransformableFrameInterface> frame, uint64_t source)
      : _video(dynamic_cast<webrtc::TransformableVideoFrameInterface *>(frame.get()) != nullptr), _source(source),
        _frame(std::move(frame)) {}

  void EncodedFrame::Init(pybind11::module &m) {
    pybind11::class_<EncodedFrame, std::shared_ptr<EncodedFrame>>(m, "RTCEncodedFrame")
        .def_property_readonly("video", &EncodedFrame::IsVideo)
        .def("getData", &EncodedFrame::GetData)
        .def("getMetadata", &EncodedFrame::GetMetadata);
  }

  pybind11::bytes EncodedFrame::GetData() {
    std::vector<uint8_t> data;
    {
      const std::scoped_lock lock(_mutex);
      if (_frame) {
        auto span = _frame->GetData();
        data.assign(span.begin(), span.end());
      }
    }
    return Bytes(data.data(), data.size());
  }

  pybind11::dict EncodedFrame::GetMetadata() {
    Metadata metadata;
    {
      const std::scoped_lock lock(_mutex);
      if (_frame) {
        metadata = MetadataOf(*_frame);
      }
    }
    pybind11::dict dict;
    for (const auto &[name, value] : metadata) {
      dict[name] = pybind11::cast(value);
    }
    return dict;
  }

  std::unique_ptr<webrtc::TransformableFrameInterface> EncodedFrame::Take() {
    const std::scoped_lock lock(_mutex);
    return std::move(_frame);
  }

} // namespace python_webrtc
