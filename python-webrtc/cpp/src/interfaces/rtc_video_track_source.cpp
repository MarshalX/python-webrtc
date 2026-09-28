//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_video_track_source.h"

#include <chrono>
#include <cstring>

#include <api/video/i420_buffer.h>
#include <rtc_base/time_utils.h>

namespace python_webrtc {

  RTCVideoTrackSource::RTCVideoTrackSource(bool isScreencast, std::optional<bool> needsDenoising)
      : _isScreencast(isScreencast), _needsDenoising(needsDenoising) {}

  RTCVideoTrackSource::~RTCVideoTrackSource() {
    {
      std::lock_guard<std::mutex> lock(_cameraMutex);
      _stopping = true;
    }
    _cameraStop.notify_all();
    // the camera thread never holds a reference, so the source isn't destroyed on it
    if (_camera.joinable()) {
      _camera.join();
    }
  }

  void RTCVideoTrackSource::StartCamera(int width, int height, double frameRate) {
    _camera = std::thread([this, width, height, frameRate]() { RunCamera(width, height, frameRate); });
  }

  void RTCVideoTrackSource::RunCamera(int width, int height, double frameRate) {
    auto interval = std::chrono::microseconds(static_cast<int64_t>(1000000 / frameRate));
    auto next = std::chrono::steady_clock::now();
    for (uint32_t frame = 0;; ++frame) {
      {
        std::unique_lock<std::mutex> lock(_cameraMutex);
        if (_cameraStop.wait_until(lock, next, [this]() { return _stopping; })) {
          return;
        }
      }
      next += interval;

      // a gradient moving across the frame, with a moving block, so that encoders have work to do
      auto buffer = webrtc::I420Buffer::Create(width, height);
      for (int y = 0; y < height; ++y) {
        auto row = buffer->MutableDataY() + y * buffer->StrideY();
        for (int x = 0; x < width; ++x) {
          row[x] = static_cast<uint8_t>(x + y + frame * 4);
        }
      }
      std::memset(buffer->MutableDataU(), static_cast<int>(64 + frame % 128), buffer->StrideU() * ((height + 1) / 2));
      std::memset(buffer->MutableDataV(), static_cast<int>(192 - frame % 128), buffer->StrideV() * ((height + 1) / 2));
      int block = std::min(width, height) / 4;
      int left = static_cast<int>((frame * 8) % std::max(1, width - block));
      for (int y = 0; y < block; ++y) {
        std::memset(buffer->MutableDataY() + (height / 3 + y) * buffer->StrideY() + left, 255, block);
      }

      PushFrame(webrtc::VideoFrame::Builder()
                    .set_video_frame_buffer(buffer)
                    .set_timestamp_us(webrtc::TimeMicros())
                    .build());
    }
  }

  void RTCVideoTrackSource::PushFrame(const webrtc::VideoFrame &frame) {
    _width = frame.width();
    _height = frame.height();
    _broadcaster.OnFrame(frame);
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
