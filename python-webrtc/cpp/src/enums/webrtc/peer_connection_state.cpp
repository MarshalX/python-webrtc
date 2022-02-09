//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <api/peer_connection_interface.h>

#include "peer_connection_state.h"

namespace python_webrtc {

  void PeerConnectionState::Init(pybind11::module &m) {
    // TODO review public name cuz mb shouldn't be as separated enum. accessible only by
    // connectionState = RTCPeerConnection.connectionState;
    pybind11::enum_<webrtc::PeerConnectionInterface::PeerConnectionState>(m, "RTCPeerConnectionState")
        .value("new", webrtc::PeerConnectionInterface::PeerConnectionState::kNew)
        .value("connecting", webrtc::PeerConnectionInterface::PeerConnectionState::kConnecting)
        .value("connected", webrtc::PeerConnectionInterface::PeerConnectionState::kConnected)
        .value("disconnected", webrtc::PeerConnectionInterface::PeerConnectionState::kDisconnected)
        .value("failed", webrtc::PeerConnectionInterface::PeerConnectionState::kFailed)
        .value("closed", webrtc::PeerConnectionInterface::PeerConnectionState::kClosed)
        .export_values();
  }

}
