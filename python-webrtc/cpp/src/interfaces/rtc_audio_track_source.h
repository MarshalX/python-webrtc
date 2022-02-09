//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>

#include <webrtc/pc/local_audio_source.h>

#include "peer_connection_factory.h"
#include "../models/python_webrtc/rtc_on_data_event.h"

namespace python_webrtc {

  class RTCAudioTrackSource : public webrtc::LocalAudioSource {
  public:
    RTCAudioTrackSource() = default;

    ~RTCAudioTrackSource() override;

    SourceState state() const override;

    bool remote() const override;

    void PushData(RTCOnDataEvent &);

    void AddSink(webrtc::AudioTrackSinkInterface *) override;

    void RemoveSink(webrtc::AudioTrackSinkInterface *) override;

  private:
    PeerConnectionFactory *_factory = PeerConnectionFactory::GetOrCreateDefault();

    std::atomic<webrtc::AudioTrackSinkInterface *> _sink = {nullptr};
  };

} // namespace python_webrtc
