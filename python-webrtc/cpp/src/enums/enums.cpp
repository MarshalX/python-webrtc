//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "enums.h"

#include "webrtc/peer_connection_state.h"
#include "webrtc/ice_connection_state.h"
#include "webrtc/ice_gathering_state.h"
#include "webrtc/sdp_type.h"
#include "webrtc/track_state.h"
#include "webrtc/source_state.h"

namespace python_webrtc {

  void Enums::Init(pybind11::module &m) {
    // webrtc

    PeerConnectionState::Init(m);
    IceConnectionState::Init(m);
    IceGatheringState::Init(m);

    SdpType::Init(m);

    TrackState::Init(m);
    SourceState::Init(m);

    // python_webrtc
  }
}
