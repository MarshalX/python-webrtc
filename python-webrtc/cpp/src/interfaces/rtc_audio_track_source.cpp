//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_audio_track_source.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <vector>

namespace python_webrtc {

  webrtc::MediaSourceInterface::SourceState RTCAudioTrackSource::state() const {
    return _ended ? webrtc::MediaSourceInterface::SourceState::kEnded
                  : webrtc::MediaSourceInterface::SourceState::kLive;
  }

  bool RTCAudioTrackSource::remote() const {
    return false;
  }

  void RTCAudioTrackSource::AddSink(webrtc::AudioTrackSinkInterface *sink) {
    const std::scoped_lock lock(_sinkMutex);
    if (std::ranges::find(_sinks, sink) == _sinks.end()) {
      _sinks.push_back(sink);
    }
  }

  void RTCAudioTrackSource::RemoveSink(webrtc::AudioTrackSinkInterface *sink) {
    const std::scoped_lock lock(_sinkMutex);
    std::erase(_sinks, sink);
  }

  void RTCAudioTrackSource::End() {
    if (!_ended.exchange(true)) {
      FireOnChanged();
    }
  }

  void RTCAudioTrackSource::PushSamples(const void *samples, int bitsPerSample, int sampleRate, size_t channels,
                                        size_t frames) {
    const std::scoped_lock lock(_sinkMutex);
    for (auto *sink : _sinks) {
      sink->OnData(samples, bitsPerSample, sampleRate, channels, frames, std::nullopt);
    }
  }

  void RTCAudioTrackSource::StartMicrophone() {
    constexpr int sampleRate = 48000;
    constexpr auto interval = std::chrono::milliseconds(10);
    constexpr size_t frames = sampleRate * interval.count() / 1000;
    constexpr int bitsPerSample = 16;
    // quiet noise (within 256 of silence), from a linear congruential generator (Numerical Recipes constants)
    constexpr uint32_t multiplier = 1664525;
    constexpr uint32_t increment = 1013904223;
    constexpr int seedShift = 16;
    constexpr int amplitude = 256;
    // the thread never holds a reference to the source, so the source isn't destroyed on it
    auto tick = [this, samples = std::vector<int16_t>(frames), seed = uint32_t{1}]() mutable {
      for (auto &sample : samples) {
        seed = (seed * multiplier) + increment;
        sample = static_cast<int16_t>((static_cast<int32_t>(seed >> seedShift) % (2 * amplitude)) - amplitude);
      }
      PushSamples(samples.data(), bitsPerSample, sampleRate, 1, frames);
    };
    _control = std::make_shared<SourceControl>();
    _control->microphone = true;
    _microphone.Start(interval, std::move(tick));
  }

} // namespace python_webrtc
