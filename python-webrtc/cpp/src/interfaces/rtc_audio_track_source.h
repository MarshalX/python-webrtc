//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>

#include <api/media_stream_interface.h>
#include <api/notifier.h>

#include "peer_connection_factory.h"
#include "../models/python_webrtc/rtc_on_data_event.h"

namespace python_webrtc {

  class RTCAudioTrackSource : public webrtc::Notifier<webrtc::AudioSourceInterface> {
  public:
    RTCAudioTrackSource() = default;

    SourceState state() const override;

    bool remote() const override;

    void PushData(RTCOnDataEvent &);

    void AddSink(webrtc::AudioTrackSinkInterface *) override;

    void RemoveSink(webrtc::AudioTrackSinkInterface *) override;

  private:
    std::atomic<webrtc::AudioTrackSinkInterface *> _sink = {nullptr};
  };

} // namespace python_webrtc
