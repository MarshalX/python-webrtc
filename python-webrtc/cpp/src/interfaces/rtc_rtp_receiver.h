//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>

#include <api/rtp_receiver_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCRtpReceiver {
  public:
    explicit RTCRtpReceiver(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpReceiverInterface>);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &holder();

    std::shared_ptr<MediaStreamTrack> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> _receiver;

    // the receiver owns wrappers of its track and current transport
    std::mutex _mutex;
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<RTCDtlsTransport> _transport;
  };

} // namespace python_webrtc
