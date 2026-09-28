//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_audio_track_source.h"

#include <chrono>

namespace python_webrtc {

  webrtc::MediaSourceInterface::SourceState RTCAudioTrackSource::state() const {
    return webrtc::MediaSourceInterface::SourceState::kLive;
  }

  bool RTCAudioTrackSource::remote() const {
    return false;
  }

  RTCAudioTrackSource::~RTCAudioTrackSource() {
    {
      std::lock_guard<std::mutex> lock(_microphoneMutex);
      _stopping = true;
    }
    _microphoneStop.notify_all();
    // the microphone thread never holds a reference, so the source isn't destroyed on it
    if (_microphone.joinable()) {
      _microphone.join();
    }
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
    _microphone = std::thread([this]() { RunMicrophone(); });
  }

  void RTCAudioTrackSource::RunMicrophone() {
    constexpr int sampleRate = 48000;
    constexpr size_t frames = sampleRate / 100;
    std::vector<int16_t> samples(frames);
    uint32_t seed = 1;
    auto next = std::chrono::steady_clock::now();
    while (true) {
      {
        std::unique_lock<std::mutex> lock(_microphoneMutex);
        if (_microphoneStop.wait_until(lock, next, [this]() { return _stopping; })) {
          return;
        }
      }
      next += std::chrono::milliseconds(10);
      for (auto &sample: samples) {
        seed = seed * 1664525 + 1013904223;
        sample = static_cast<int16_t>(static_cast<int32_t>(seed >> 16) % 512 - 256);
      }
      PushSamples(samples.data(), 16, sampleRate, 1, frames);
    }
  }

} // namespace python_webrtc
