//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>

#include <api/rtp_sender_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCRtpSender {
  public:
    explicit RTCRtpSender(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpSenderInterface>);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &holder();

    std::optional<std::shared_ptr<MediaStreamTrack>> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender() { return _sender; }

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpSenderInterface> _sender;

    // the sender owns wrappers of its current track and transport
    std::mutex _mutex;
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<RTCDtlsTransport> _transport;
  };

} // namespace python_webrtc
