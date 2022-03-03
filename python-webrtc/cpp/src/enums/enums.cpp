//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "enums.h"

#include "webrtc/peer_connection_state.h"
#include "webrtc/ice_connection_state.h"
#include "webrtc/ice_gathering_state.h"
#include "webrtc/sdp_type.h"
#include "webrtc/track_state.h"
#include "webrtc/source_state.h"
#include "webrtc/media_type.h"
#include "webrtc/rtp_transceiver_direction.h"
#include "webrtc/cricket_ice_gathering_state.h"
#include "webrtc/rtc_ice_role.h"
#include "webrtc/rtc_ice_transport_state.h"
#include "webrtc/dtls_transport_state.h"
#include "python_webrtc/rtc_ice_component.h"

namespace python_webrtc {

  void Enums::Init(pybind11::module &m) {
    // webrtc

    PeerConnectionState::Init(m);
    IceConnectionState::Init(m);
    IceGatheringState::Init(m);

    SdpType::Init(m);

    TrackState::Init(m);
    SourceState::Init(m);
    MediaType::Init(m);

    RTPTransceiverDirection::Init(m);

    CricketIceGatheringState::Init(m);
    RTCIceRole::Init(m);
    RTCIceTransportState::Init(m);
    DtlsTransportState::Init(m);

    // python_webrtc

    RTCIceComponent_::Init(m);
  }

} // namespace python_webrtc
