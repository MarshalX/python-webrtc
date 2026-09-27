//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <api/peer_connection_interface.h>

#include "signaling_state.h"

namespace python_webrtc {

  void SignalingState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::PeerConnectionInterface::SignalingState>(m, "RTCSignalingState")
        .value("stable", webrtc::PeerConnectionInterface::SignalingState::kStable)
        .value("have_local_offer", webrtc::PeerConnectionInterface::SignalingState::kHaveLocalOffer)
        .value("have_local_pranswer", webrtc::PeerConnectionInterface::SignalingState::kHaveLocalPrAnswer)
        .value("have_remote_offer", webrtc::PeerConnectionInterface::SignalingState::kHaveRemoteOffer)
        .value("have_remote_pranswer", webrtc::PeerConnectionInterface::SignalingState::kHaveRemotePrAnswer)
        .value("closed", webrtc::PeerConnectionInterface::SignalingState::kClosed)
        .export_values();
  }

}
