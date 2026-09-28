//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <vector>

#include <api/media_stream_interface.h>
#include <api/notifier.h>

#include "peer_connection_factory.h"
#include "../models/python_webrtc/rtc_on_data_event.h"

namespace python_webrtc {

  class RTCAudioTrackSource : public webrtc::Notifier<webrtc::AudioSourceInterface> {
  public:
    RTCAudioTrackSource() = default;

    ~RTCAudioTrackSource() override;

    // Starts a synthetic microphone: quiet noise, in 10 ms frames of 48 kHz mono
    void StartMicrophone();

    SourceState state() const override;

    bool remote() const override;

    void PushData(RTCOnDataEvent &);

    void AddSink(webrtc::AudioTrackSinkInterface *) override;

    void RemoveSink(webrtc::AudioTrackSinkInterface *) override;

  private:
    void PushSamples(const void *samples, int bitsPerSample, int sampleRate, size_t channels, size_t frames);

    void RunMicrophone();

    // guards the sink, which is removed (and may be destroyed) on another thread than the one pushing data
    std::mutex _sinkMutex;
    webrtc::AudioTrackSinkInterface *_sink = nullptr;

    std::mutex _microphoneMutex;
    std::condition_variable _microphoneStop;
    bool _stopping = false;
    std::thread _microphone;
  };

} // namespace python_webrtc
