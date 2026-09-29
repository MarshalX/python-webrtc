//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "playout_audio_device.h"

#include <chrono>
#include <cstring>
#include <vector>

namespace python_webrtc {

  namespace {

    int32_t DeviceName(uint16_t index, char name[webrtc::kAdmMaxDeviceNameSize], char guid[webrtc::kAdmMaxGuidSize]) {
      if (index != 0) {
        return -1;
      }
      std::strncpy(name, "python-webrtc", webrtc::kAdmMaxDeviceNameSize - 1);
      name[webrtc::kAdmMaxDeviceNameSize - 1] = '\0';
      if (guid) {
        guid[0] = '\0';
      }
      return 0;
    }

  } // namespace

  PlayoutAudioDevice::~PlayoutAudioDevice() {
    StopPlayout();
  }

  int32_t PlayoutAudioDevice::ActiveAudioLayer(AudioLayer *audioLayer) const {
    *audioLayer = kDummyAudio;
    return 0;
  }

  int32_t PlayoutAudioDevice::RegisterAudioCallback(webrtc::AudioTransport *audioCallback) {
    std::lock_guard<std::mutex> lock(_mutex);
    _transport = audioCallback;
    return 0;
  }

  int32_t PlayoutAudioDevice::Init() {
    std::lock_guard<std::mutex> lock(_mutex);
    _initialized = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::Terminate() {
    StopPlayout();
    StopRecording();
    std::lock_guard<std::mutex> lock(_mutex);
    _initialized = false;
    return 0;
  }

  bool PlayoutAudioDevice::Initialized() const {
    std::lock_guard<std::mutex> lock(_mutex);
    return _initialized;
  }

  int32_t PlayoutAudioDevice::PlayoutDeviceName(uint16_t index, char name[webrtc::kAdmMaxDeviceNameSize],
                                                char guid[webrtc::kAdmMaxGuidSize]) {
    return DeviceName(index, name, guid);
  }

  int32_t PlayoutAudioDevice::RecordingDeviceName(uint16_t index, char name[webrtc::kAdmMaxDeviceNameSize],
                                                  char guid[webrtc::kAdmMaxGuidSize]) {
    return DeviceName(index, name, guid);
  }

  int32_t PlayoutAudioDevice::PlayoutIsAvailable(bool *available) {
    *available = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::InitPlayout() {
    std::lock_guard<std::mutex> lock(_mutex);
    _playoutInitialized = true;
    return 0;
  }

  bool PlayoutAudioDevice::PlayoutIsInitialized() const {
    std::lock_guard<std::mutex> lock(_mutex);
    return _playoutInitialized;
  }

  int32_t PlayoutAudioDevice::RecordingIsAvailable(bool *available) {
    *available = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::InitRecording() {
    std::lock_guard<std::mutex> lock(_mutex);
    _recordingInitialized = true;
    return 0;
  }

  bool PlayoutAudioDevice::RecordingIsInitialized() const {
    std::lock_guard<std::mutex> lock(_mutex);
    return _recordingInitialized;
  }

  int32_t PlayoutAudioDevice::StartPlayout() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_playout) {
      return 0;
    }
    _playout = std::make_unique<PacedThread>();
    std::vector<int16_t> samples(kFrames * kChannels);
    _playout->Start(std::chrono::milliseconds(kPullIntervalMs), [this, samples = std::move(samples)]() mutable {
      std::lock_guard<std::mutex> lock(_mutex);
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
      std::lock_guard<std::mutex> lock(_mutex);
      playout = std::move(_playout);
      _playoutInitialized = false;
    }
    // joins the thread, whose last tick may be waiting for the mutex
    playout = nullptr;
    return 0;
  }

  bool PlayoutAudioDevice::Playing() const {
    std::lock_guard<std::mutex> lock(_mutex);
    return static_cast<bool>(_playout);
  }

  int32_t PlayoutAudioDevice::StartRecording() {
    std::lock_guard<std::mutex> lock(_mutex);
    _recording = true;
    return 0;
  }

  int32_t PlayoutAudioDevice::StopRecording() {
    std::lock_guard<std::mutex> lock(_mutex);
    _recording = false;
    _recordingInitialized = false;
    return 0;
  }

  bool PlayoutAudioDevice::Recording() const {
    std::lock_guard<std::mutex> lock(_mutex);
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
