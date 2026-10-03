//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "playout_audio_device.h"

#include <chrono>
#include <cstring>
#include <span>
#include <vector>

namespace python_webrtc {

  namespace {

    // the single device, without a guid
    int32_t DeviceName(uint16_t index, std::span<char, webrtc::kAdmMaxDeviceNameSize> name, char *guid) {
      if (index != 0) {
        return -1;
      }
      std::strncpy(name.data(), "python-webrtc", name.size() - 1);
      name.back() = '\0';
      if (guid != nullptr) {
        *guid = '\0';
      }
      return 0;
    }

  } // namespace

  PlayoutAudioDevice::~PlayoutAudioDevice() {
    // this class's own, as in any destructor
    PlayoutAudioDevice::StopPlayout();
  }

  int32_t PlayoutAudioDevice::ActiveAudioLayer(AudioLayer *audioLayer) const {
    *audioLayer = kDummyAudio;
    return 0;
  }

  int32_t PlayoutAudioDevice::RegisterAudioCallback(webrtc::AudioTransport *audioCallback) {
    const std::scoped_lock lock(_mutex);
    _transport = audioCallback;
    return 0;
  }

  int32_t PlayoutAudioDevice::Init() {
    const std::scoped_lock lock(_mutex);
    _initialized = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::Terminate() {
    StopPlayout();
    StopRecording();
    const std::scoped_lock lock(_mutex);
    _initialized = false;
    return 0;
  }

  bool PlayoutAudioDevice::Initialized() const {
    const std::scoped_lock lock(_mutex);
    return _initialized;
  }

  int32_t PlayoutAudioDevice::PlayoutDeviceName(uint16_t index, char *name, char *guid) {
    return DeviceName(index, std::span<char, webrtc::kAdmMaxDeviceNameSize>(name, webrtc::kAdmMaxDeviceNameSize), guid);
  }

  int32_t PlayoutAudioDevice::RecordingDeviceName(uint16_t index, char *name, char *guid) {
    return DeviceName(index, std::span<char, webrtc::kAdmMaxDeviceNameSize>(name, webrtc::kAdmMaxDeviceNameSize), guid);
  }

  int32_t PlayoutAudioDevice::PlayoutIsAvailable(bool *available) {
    *available = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::InitPlayout() {
    const std::scoped_lock lock(_mutex);
    _playoutInitialized = true;
    return 0;
  }

  bool PlayoutAudioDevice::PlayoutIsInitialized() const {
    const std::scoped_lock lock(_mutex);
    return _playoutInitialized;
  }

  int32_t PlayoutAudioDevice::RecordingIsAvailable(bool *available) {
    *available = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::InitRecording() {
    const std::scoped_lock lock(_mutex);
    _recordingInitialized = true;
    return 0;
  }

  bool PlayoutAudioDevice::RecordingIsInitialized() const {
    const std::scoped_lock lock(_mutex);
    return _recordingInitialized;
  }

  int32_t PlayoutAudioDevice::StartPlayout() {
    const std::scoped_lock lock(_mutex);
    if (_playout) {
      return 0;
    }
    _playout = std::make_unique<PacedThread>();
    std::vector<int16_t> samples(kFrames * kChannels);
    _playout->Start(std::chrono::milliseconds(kPullIntervalMs), [this, samples = std::move(samples)]() mutable {
      const std::scoped_lock lock(_mutex);
      if (!_transport) {
        return;
      }
      size_t samplesOut = 0;
      int64_t elapsedTimeMs = -1;
      int64_t ntpTimeMs = -1;
      _transport->NeedMorePlayData(kFrames, sizeof(int16_t) * kChannels, kChannels, kSampleRate, samples.data(),
                                   samplesOut, &elapsedTimeMs, &ntpTimeMs);
    });
    return 0;
  }

  int32_t PlayoutAudioDevice::StopPlayout() {
    std::unique_ptr<PacedThread> playout;
    {
      const std::scoped_lock lock(_mutex);
      playout = std::move(_playout);
      _playoutInitialized = false;
    }
    // joins the thread, whose last tick may be waiting for the mutex
    playout = nullptr;
    return 0;
  }

  bool PlayoutAudioDevice::Playing() const {
    const std::scoped_lock lock(_mutex);
    return static_cast<bool>(_playout);
  }

  int32_t PlayoutAudioDevice::StartRecording() {
    const std::scoped_lock lock(_mutex);
    _recording = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::StopRecording() {
    const std::scoped_lock lock(_mutex);
    _recording = false;
    _recordingInitialized = false;
    return 0;
  }

  bool PlayoutAudioDevice::Recording() const {
    const std::scoped_lock lock(_mutex);
    return _recording;
  }

  int32_t PlayoutAudioDevice::SpeakerVolumeIsAvailable(bool *available) {
    *available = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::MicrophoneVolumeIsAvailable(bool *available) {
    *available = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::SpeakerMuteIsAvailable(bool *available) {
    *available = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::MicrophoneMuteIsAvailable(bool *available) {
    *available = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::StereoPlayoutIsAvailable(bool *available) const {
    *available = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::StereoPlayout(bool *enabled) const {
    *enabled = kChannels == 2;
    return 0;
  }

  int32_t PlayoutAudioDevice::StereoRecordingIsAvailable(bool *available) const {
    *available = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::StereoRecording(bool *enabled) const {
    *enabled = false;
    return 0;
  }

  int32_t PlayoutAudioDevice::PlayoutDelay(uint16_t *delayMS) const {
    *delayMS = 0;
    return 0;
  }

} // namespace python_webrtc
