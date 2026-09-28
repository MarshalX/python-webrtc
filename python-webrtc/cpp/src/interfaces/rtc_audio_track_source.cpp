//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_audio_track_source.h"

#include <chrono>
#include <cstdint>
#include <vector>

namespace python_webrtc {

  webrtc::MediaSourceInterface::SourceState RTCAudioTrackSource::state() const {
    return webrtc::MediaSourceInterface::SourceState::kLive;
  }

  bool RTCAudioTrackSource::remote() const {
    return false;
  }

  void RTCAudioTrackSource::AddSink(webrtc::AudioTrackSinkInterface *sink) {
    std::lock_guard<std::mutex> lock(_sinkMutex);
    _sink = sink;
  }

  void RTCAudioTrackSource::RemoveSink(webrtc::AudioTrackSinkInterface *sink) {
    std::lock_guard<std::mutex> lock(_sinkMutex);
    if (_sink == sink) {
      _sink = nullptr;
    }
  }

  void RTCAudioTrackSource::PushSamples(
      const void *samples, int bitsPerSample, int sampleRate, size_t channels, size_t frames) {
    std::lock_guard<std::mutex> lock(_sinkMutex);
    if (_sink) {
      _sink->OnData(samples, bitsPerSample, sampleRate, channels, frames);
    }
  }

  void RTCAudioTrackSource::PushData(RTCOnDataEvent &data) {
    PushSamples(data.audioData.data(), data.bitsPerSample, data.sampleRate, data.channelCount, data.numberOfFrames);
  }

  void RTCAudioTrackSource::StartMicrophone() {
    constexpr int sampleRate = 48000;
    constexpr size_t frames = sampleRate / 100;
    // the thread never holds a reference to the source, so the source isn't destroyed on it
    auto tick = [this, samples = std::vector<int16_t>(frames), seed = uint32_t(1)]() mutable {
      for (auto &sample: samples) {
        // quiet noise (within 256 of silence), from a linear congruential generator (Numerical Recipes constants)
        seed = seed * 1664525 + 1013904223;
        sample = static_cast<int16_t>(static_cast<int32_t>(seed >> 16) % 512 - 256);
      }
      PushSamples(samples.data(), 16, sampleRate, 1, frames);
    };
    _microphone.Start(std::chrono::milliseconds(10), std::move(tick));
  }

} // namespace python_webrtc
