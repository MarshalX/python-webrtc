//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_TRACK_MONITOR_H_
#define PYTHON_WEBRTC_MEDIA_TRACK_MONITOR_H_

#include <algorithm>
#include <array>
#include <cstdint>
#include <mutex>
#include <optional>

#include <api/media_stream_interface.h>
#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>
#include <rtc_base/time_utils.h>

namespace python_webrtc {

  // What a track carries, for its settings: the size and rate of its frames, the format of its audio
  class TrackMonitor : public webrtc::VideoSinkInterface<webrtc::VideoFrame>, public webrtc::AudioTrackSinkInterface {
  public:
    struct Video {
      int width;
      int height;
      // measured over the last frames, if there were enough of them recently
      std::optional<double> frameRate;
    };

    struct Audio {
      int sampleRate;
      int channels;
      int bitsPerSample;
    };

    void OnFrame(const webrtc::VideoFrame &frame) override {
      auto now = webrtc::TimeMicros();
      const std::scoped_lock lock(_mutex);
      if (_video && (_video->width != frame.width() || _video->height != frame.height())) {
        // the rate is measured from the new size on, as the source changed
        _count = 0;
      }
      _video = Video{.width = frame.width(), .height = frame.height(), .frameRate = std::nullopt};
      _times[_count % _times.size()] = now;
      _count++;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): libwebrtc's signature
    void OnData(const void * /*audioData*/, int bitsPerSample, int sampleRate, size_t channels,
                size_t /*frames*/) override {
      const std::scoped_lock lock(_mutex);
      _audio = Audio{.sampleRate = sampleRate, .channels = static_cast<int>(channels), .bitsPerSample = bitsPerSample};
    }

    void OnData(const void *audioData, int bitsPerSample, int sampleRate, size_t channels, size_t frames,
                std::optional<int64_t> /*absoluteCaptureTimestampMs*/) override {
      OnData(audioData, bitsPerSample, sampleRate, channels, frames);
    }

    std::optional<Video> video() {
      const std::scoped_lock lock(_mutex);
      if (!_video) {
        return std::nullopt;
      }
      auto video = *_video;
      const size_t samples = std::min<size_t>(_count, _times.size());
      if (samples >= 2) {
        auto last = _times[(_count - 1) % _times.size()];
        auto first = _times[(_count - samples) % _times.size()];
        // frames that stopped more than a second ago have no rate anymore
        if (last > first && webrtc::TimeMicros() - last < webrtc::kNumMicrosecsPerSec) {
          video.frameRate =
              static_cast<double>((samples - 1) * webrtc::kNumMicrosecsPerSec) / static_cast<double>(last - first);
        }
      }
      return video;
    }

    std::optional<Audio> audio() {
      const std::scoped_lock lock(_mutex);
      return _audio;
    }

  private:
    std::mutex _mutex;
    std::optional<Video> _video;
    std::optional<Audio> _audio;
    // arrival times of the last frames, in microseconds
    static constexpr size_t kTimedFrames = 30;
    std::array<int64_t, kTimedFrames> _times{};
    size_t _count = 0;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_TRACK_MONITOR_H_
