//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_PLAYOUT_AUDIO_DEVICE_H_
#define PYTHON_WEBRTC_MEDIA_PLAYOUT_AUDIO_DEVICE_H_

#include <cstdint>
#include <memory>
#include <mutex>

#include <api/audio/audio_device.h>
#include <api/audio/audio_device_defines.h>

#include "../utils/paced_thread.h"

namespace python_webrtc {

  // An audio device without hardware: records nothing, and pulls playout every 10 ms so remote tracks get audio
  class PlayoutAudioDevice : public webrtc::AudioDeviceModule {
  public:
    static constexpr int kSampleRate = 48000;
    static constexpr size_t kChannels = 2;
    static constexpr int kPullIntervalMs = 10;
    static constexpr size_t kFrames = kSampleRate * kPullIntervalMs / 1000;

    ~PlayoutAudioDevice() override;

    PlayoutAudioDevice() = default;

    PlayoutAudioDevice(const PlayoutAudioDevice &) = delete;
    PlayoutAudioDevice &operator=(const PlayoutAudioDevice &) = delete;

    int32_t ActiveAudioLayer(AudioLayer *audioLayer) const override;

    int32_t RegisterAudioCallback(webrtc::AudioTransport *audioCallback) override;

    int32_t Init() override;

    int32_t Terminate() override;

    bool Initialized() const override;

    int16_t PlayoutDevices() override { return 1; }

    int16_t RecordingDevices() override { return 1; }

    // name and guid point to kAdmMaxDeviceNameSize and kAdmMaxGuidSize chars
    int32_t PlayoutDeviceName(uint16_t index, char *name, char *guid) override;

    int32_t RecordingDeviceName(uint16_t index, char *name, char *guid) override;

    int32_t SetPlayoutDevice(uint16_t /*index*/) override { return 0; }

    int32_t SetPlayoutDevice(WindowsDeviceType /*device*/) override { return 0; }

    int32_t SetRecordingDevice(uint16_t /*index*/) override { return 0; }

    int32_t SetRecordingDevice(WindowsDeviceType /*device*/) override { return 0; }

    int32_t PlayoutIsAvailable(bool *available) override;

    int32_t InitPlayout() override;

    bool PlayoutIsInitialized() const override;

    int32_t RecordingIsAvailable(bool *available) override;

    int32_t InitRecording() override;

    bool RecordingIsInitialized() const override;

    int32_t StartPlayout() override;

    int32_t StopPlayout() override;

    bool Playing() const override;

    int32_t StartRecording() override;

    int32_t StopRecording() override;

    bool Recording() const override;

    int32_t InitSpeaker() override { return 0; }

    bool SpeakerIsInitialized() const override { return true; }

    int32_t InitMicrophone() override { return 0; }

    bool MicrophoneIsInitialized() const override { return true; }

    int32_t SpeakerVolumeIsAvailable(bool *available) override;

    int32_t SetSpeakerVolume(uint32_t /*volume*/) override { return -1; }

    int32_t SpeakerVolume(uint32_t * /*volume*/) const override { return -1; }

    int32_t MaxSpeakerVolume(uint32_t * /*maxVolume*/) const override { return -1; }

    int32_t MinSpeakerVolume(uint32_t * /*minVolume*/) const override { return -1; }

    int32_t MicrophoneVolumeIsAvailable(bool *available) override;

    int32_t SetMicrophoneVolume(uint32_t /*volume*/) override { return -1; }

    int32_t MicrophoneVolume(uint32_t * /*volume*/) const override { return -1; }

    int32_t MaxMicrophoneVolume(uint32_t * /*maxVolume*/) const override { return -1; }

    int32_t MinMicrophoneVolume(uint32_t * /*minVolume*/) const override { return -1; }

    int32_t SpeakerMuteIsAvailable(bool *available) override;

    int32_t SetSpeakerMute(bool /*enable*/) override { return -1; }

    int32_t SpeakerMute(bool * /*enabled*/) const override { return -1; }

    int32_t MicrophoneMuteIsAvailable(bool *available) override;

    int32_t SetMicrophoneMute(bool /*enable*/) override { return -1; }

    int32_t MicrophoneMute(bool * /*enabled*/) const override { return -1; }

    int32_t StereoPlayoutIsAvailable(bool *available) const override;

    int32_t SetStereoPlayout(bool /*enable*/) override { return 0; }

    int32_t StereoPlayout(bool *enabled) const override;

    int32_t StereoRecordingIsAvailable(bool *available) const override;

    int32_t SetStereoRecording(bool /*enable*/) override { return 0; }

    int32_t StereoRecording(bool *enabled) const override;

    int32_t PlayoutDelay(uint16_t *delayMS) const override;

    bool BuiltInAECIsAvailable() const override { return false; }

    bool BuiltInAGCIsAvailable() const override { return false; }

    bool BuiltInNSIsAvailable() const override { return false; }

    int32_t EnableBuiltInAEC(bool /*enable*/) override { return -1; }

    int32_t EnableBuiltInAGC(bool /*enable*/) override { return -1; }

    int32_t EnableBuiltInNS(bool /*enable*/) override { return -1; }

  private:
    mutable std::mutex _mutex;
    webrtc::AudioTransport *_transport = nullptr;
    bool _initialized = false;
    bool _playoutInitialized = false;
    bool _recordingInitialized = false;
    bool _recording = false;
    // the playout thread while playing, destroyed without the mutex: its ticks take it
    std::unique_ptr<PacedThread> _playout;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_PLAYOUT_AUDIO_DEVICE_H_
