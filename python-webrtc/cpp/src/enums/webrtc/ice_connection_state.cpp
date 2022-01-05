//
// Created by Il'ya Semyonov on 1/5/22.
//

#include <api/peer_connection_interface.h>

#include "ice_connection_state.h"

namespace python_webrtc {

  void IceConnectionState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::PeerConnectionInterface::IceConnectionState>(m,"RTCIceConnectionState")
        .value("new", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionNew)
        .value("checking", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionChecking)
        .value("connected", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionConnected)
        .value("completed", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionCompleted)
        .value("failed", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionFailed)
        .value("disconnected", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionDisconnected)
        .value("closed", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionClosed)
        .value("max", webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionMax)
        .export_values();
  }

}
