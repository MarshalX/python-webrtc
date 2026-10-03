//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_video_track_source.h"

#include <algorithm>
#include <chrono>
#include <cstring>

#include <api/video/i420_buffer.h>
#include <rtc_base/time_utils.h>

namespace python_webrtc {

  RTCVideoTrackSource::RTCVideoTrackSource(bool isScreencast, std::optional<bool> needsDenoising)
      : _isScreencast(isScreencast), _needsDenoising(needsDenoising) {}

  RTCVideoTrackSource::~RTCVideoTrackSource() {
    if (_control) {
      const std::scoped_lock lock(_control->mutex);
      _control->camera = nullptr;
    }
  }

  void RTCVideoTrackSource::StartCamera(int width, int height, double frameRate) {
    if (!_control) {
      _control = std::make_shared<SourceControl>();
      _control->camera = this;
    }
    constexpr double usPerSecond = 1e6;
    auto interval = std::chrono::microseconds(static_cast<int64_t>(usPerSecond / frameRate));
    const std::scoped_lock lock(_cameraMutex);
    // the previous camera stops first: one thread draws at a time
    _camera = nullptr;
    _cameraWidth = width;
    _cameraHeight = height;
    _cameraFrameRate = frameRate;
    _camera = std::make_unique<PacedThread>();
    // the thread never holds a reference to the source, so the source isn't destroyed on it
    _camera->Start(interval,
                   [this, width, height, frame = uint32_t{0}]() mutable { DrawFrame(width, height, frame++); });
  }

  bool RTCVideoTrackSource::IsCamera(int *width, int *height, double *frameRate) {
    const std::scoped_lock lock(_cameraMutex);
    if (!_camera) {
      return false;
    }
    *width = _cameraWidth;
    *height = _cameraHeight;
    *frameRate = _cameraFrameRate;
    return true;
  }

  void RTCVideoTrackSource::DrawFrame(int width, int height, uint32_t frame) {
    // a gradient moving across the frame, with a moving block, so that encoders have work to do
    auto buffer = webrtc::I420Buffer::Create(width, height);
    for (int y = 0; y < height; ++y) {
      auto *row = buffer->MutableDataY() + (static_cast<std::ptrdiff_t>(y) * buffer->StrideY());
      for (int x = 0; x < width; ++x) {
        row[x] = static_cast<uint8_t>(x + y + (frame * 4));
      }
    }
    // the colors drift through a range of the chroma planes, the block is white
    constexpr uint32_t chromaRange = 128;
    constexpr int uBase = 64;
    constexpr int vBase = 192;
    constexpr int white = 255;
    constexpr uint32_t blockSpeed = 8;
    std::memset(buffer->MutableDataU(), static_cast<int>(uBase + (frame % chromaRange)),
                static_cast<size_t>(buffer->StrideU()) * ((height + 1) / 2));
    std::memset(buffer->MutableDataV(), static_cast<int>(vBase - (frame % chromaRange)),
                static_cast<size_t>(buffer->StrideV()) * ((height + 1) / 2));
    const int block = std::min(width, height) / 4;
    const int left = static_cast<int>((frame * blockSpeed) % std::max(1, width - block));
    for (int y = 0; y < block; ++y) {
      std::memset(buffer->MutableDataY() + (static_cast<std::ptrdiff_t>((height / 3) + y) * buffer->StrideY()) + left,
                  white, block);
    }

    PushFrame(
        webrtc::VideoFrame::Builder().set_video_frame_buffer(buffer).set_timestamp_us(webrtc::TimeMicros()).build());
  }

  void RTCVideoTrackSource::PushFrame(const webrtc::VideoFrame &frame) {
    _width = frame.width();
    _height = frame.height();
    _broadcaster.OnFrame(frame);
  }

  void RTCVideoTrackSource::End() {
    if (!_ended.exchange(true)) {
      FireOnChanged();
    }
  }

  bool RTCVideoTrackSource::GetStats(Stats *stats) {
    if (_width == 0) {
      return false;
    }
    stats->input_width = _width;
    stats->input_height = _height;
    return true;
  }

  void RTCVideoTrackSource::AddOrUpdateSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink,
                                            const webrtc::VideoSinkWants &wants) {
    _broadcaster.AddOrUpdateSink(sink, wants);
  }

  void RTCVideoTrackSource::RemoveSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) {
    _broadcaster.RemoveSink(sink);
  }

} // namespace python_webrtc
