//
// Created by Il'ya Semyonov on 1/5/22.
//

#include <api/peer_connection_interface.h>

#include "peer_connection_state.h"

namespace python_webrtc {

  void PeerConnectionState::Init(pybind11::module &m) {
    // TODO review public name cuz mb shouldn't be as separated enum. accessible only by
    // connectionState = RTCPeerConnection.connectionState;
    pybind11::enum_<webrtc::PeerConnectionInterface::PeerConnectionState>(m,"RTCPeerConnectionState")
        .value("new", webrtc::PeerConnectionInterface::PeerConnectionState::kNew)
        .value("connecting", webrtc::PeerConnectionInterface::PeerConnectionState::kConnecting)
        .value("connected", webrtc::PeerConnectionInterface::PeerConnectionState::kConnected)
        .value("disconnected", webrtc::PeerConnectionInterface::PeerConnectionState::kDisconnected)
        .value("failed", webrtc::PeerConnectionInterface::PeerConnectionState::kFailed)
        .value("closed", webrtc::PeerConnectionInterface::PeerConnectionState::kClosed)
        .export_values();
  }

}
