//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_AUDIO_TRACK_SOURCE_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_AUDIO_TRACK_SOURCE_H_

#include <atomic>
#include <memory>
#include <mutex>
#include <vector>

#include <api/media_stream_interface.h>
#include <api/notifier.h>

#include "../media/source_control.h"
#include "../utils/paced_thread.h"

namespace python_webrtc {

  class RTCAudioTrackSource : public webrtc::Notifier<webrtc::AudioSourceInterface> {
  public:
    RTCAudioTrackSource() = default;

    // Starts a synthetic microphone: quiet noise, in 10 ms frames of 48 kHz mono
    void StartMicrophone();

    // what reaches the microphone from its tracks, once started
    std::shared_ptr<SourceControl> control() { return _control; }

    SourceState state() const override;

    bool remote() const override;

    void PushSamples(const void *samples, int bitsPerSample, int sampleRate, size_t channels, size_t frames);

    // ends the tracks of the source; must be called on the signaling thread, where they observe it
    void End();

    void AddSink(webrtc::AudioTrackSinkInterface * /*unused*/) override;

    void RemoveSink(webrtc::AudioTrackSinkInterface * /*unused*/) override;

  private:
    // guards the sinks (the sender, processors), removed (and maybe destroyed) on other threads than the one pushing
    std::mutex _sinkMutex;
    std::vector<webrtc::AudioTrackSinkInterface *> _sinks;
    std::atomic<bool> _ended{false};
    std::shared_ptr<SourceControl> _control;

    // last, to be stopped before the rest is destroyed
    PacedThread _microphone;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_AUDIO_TRACK_SOURCE_H_
