//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "interfaces.h"

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "media_stream.h"
#include "rtc_ice_transport.h"
#include "rtc_dtls_transport.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_receiver.h"
#include "rtc_rtp_transceiver.h"
#include "rtc_audio_source.h"
#include "rtc_peer_connection.h"

namespace python_webrtc {

  void Interfaces::Init(pybind11::module &m) {
    PeerConnectionFactory::Init(m);
    MediaStreamTrack::Init(m);
    MediaStream::Init(m);
    RTCIceTransport::Init(m);
    RTCDtlsTransport::Init(m);
    RTCRtpSender::Init(m);
    RTCRtpReceiver::Init(m);
    RTCRtpTransceiver::Init(m);
    RTCPeerConnection::Init(m);
    RTCAudioSource::Init(m);
  }
}
