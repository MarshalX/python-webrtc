//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_video_source.h"

#include <api/video/i420_buffer.h>
#include <rtc_base/crypto_random.h>
#include <rtc_base/time_utils.h>

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCVideoSource::RTCVideoSource(bool isScreencast, std::optional<bool> needsDenoising)
      : _factory(PeerConnectionFactory::GetOrCreateDefault()),
        _source(webrtc::make_ref_counted<RTCVideoTrackSource>(isScreencast, needsDenoising)) {}

  void RTCVideoSource::Init(pybind11::module &m) {
    pybind11::class_<RTCVideoSource, std::shared_ptr<RTCVideoSource>>(m, "RTCVideoSource")
        .def(pybind11::init<bool, std::optional<bool>>(), nogil(),
             pybind11::arg("isScreencast"), pybind11::arg("needsDenoising"))
        .def_property_readonly("isScreencast", nogil_fn(&RTCVideoSource::GetIsScreencast))
        .def_property_readonly("needsDenoising", nogil_fn(&RTCVideoSource::GetNeedsDenoising))
        .def("createTrack", &RTCVideoSource::CreateTrack, nogil())
        .def("onFrame", &RTCVideoSource::OnFrame, nogil(), pybind11::arg("width"), pybind11::arg("height"),
             pybind11::arg("i420"), pybind11::arg("rotation"), pybind11::arg("timestampUs"));
  }

  bool RTCVideoSource::GetIsScreencast() {
    return _source->is_screencast();
  }

  std::optional<bool> RTCVideoSource::GetNeedsDenoising() {
    return _source->needs_denoising();
  }

  std::shared_ptr<MediaStreamTrack> RTCVideoSource::CreateTrack() {
    auto track = _factory->factory()->CreateVideoTrack(_source, webrtc::CreateRandomUuid());
    return MediaStreamTrack::holder().GetOrCreate(_factory, track);
  }

  void RTCVideoSource::OnFrame(int width, int height, const std::string &i420, int rotation,
                               std::optional<int64_t> timestampUs) {
    if (width <= 0 || height <= 0) {
      throw RTCException(webrtc::RTCErrorType::INVALID_RANGE, "The frame must have a positive width and height");
    }
    size_t lumaSize = static_cast<size_t>(width) * height;
    int chromaWidth = (width + 1) / 2;
    size_t chromaSize = static_cast<size_t>(chromaWidth) * ((height + 1) / 2);
    size_t size = lumaSize + 2 * chromaSize;
    if (i420.size() != size) {
      throw RTCException(webrtc::RTCErrorType::INVALID_PARAMETER,
                         "The data of an I420 frame of this size must be " + std::to_string(size) + " bytes");
    }
    if (rotation != 0 && rotation != 90 && rotation != 180 && rotation != 270) {
      throw RTCException(webrtc::RTCErrorType::INVALID_RANGE, "The rotation must be 0, 90, 180 or 270");
    }

    auto data = reinterpret_cast<const uint8_t *>(i420.data());
    auto buffer = webrtc::I420Buffer::Copy(
        width, height,
        data, width,
        data + lumaSize, chromaWidth,
        data + lumaSize + chromaSize, chromaWidth);
    _source->PushFrame(webrtc::VideoFrame::Builder()
                           .set_video_frame_buffer(buffer)
                           .set_rotation(static_cast<webrtc::VideoRotation>(rotation))
                           .set_timestamp_us(timestampUs.value_or(webrtc::TimeMicros()))
                           .build());
  }

  webrtc::scoped_refptr<webrtc::VideoTrackInterface> RTCVideoSource::CreateCameraTrack(
      const std::shared_ptr<PeerConnectionFactory> &factory, int width, int height, double frameRate) {
    auto source = webrtc::make_ref_counted<RTCVideoTrackSource>(false, std::nullopt);
    source->StartCamera(width, height, frameRate);
    return factory->factory()->CreateVideoTrack(source, webrtc::CreateRandomUuid());
  }

} // namespace python_webrtc
