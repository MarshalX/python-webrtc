//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/rtp_sender_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCRtpSender {
  public:
    explicit RTCRtpSender(PeerConnectionFactory *, webrtc::scoped_refptr<webrtc::RtpSenderInterface>);

    static RTCRtpSender *Create(PeerConnectionFactory *, webrtc::scoped_refptr<webrtc::RtpSenderInterface>);

    ~RTCRtpSender();

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCRtpSender *, webrtc::scoped_refptr<webrtc::RtpSenderInterface>, PeerConnectionFactory *
    > *holder();

    std::optional<MediaStreamTrack *> GetTrack();

    std::optional<RTCDtlsTransport *> GetTransport();

    webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender() { return _sender; }

  private:
    PeerConnectionFactory *_factory;
    webrtc::scoped_refptr<webrtc::RtpSenderInterface> _sender;
  };

} // namespace python_webrtc
