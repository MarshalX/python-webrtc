//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCRtpReceiver {
  public:
    explicit RTCRtpReceiver(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpReceiverInterface>);

    static RTCRtpReceiver *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpReceiverInterface>);

    ~RTCRtpReceiver();

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCRtpReceiver *, rtc::scoped_refptr<webrtc::RtpReceiverInterface>, PeerConnectionFactory *
    > *holder();

    MediaStreamTrack *GetTrack();

    std::optional<RTCDtlsTransport *> GetTransport();

  private:
    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::RtpReceiverInterface> _receiver;
  };

} // namespace python_webrtc
