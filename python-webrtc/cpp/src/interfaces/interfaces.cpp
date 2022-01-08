//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "interfaces.h"

#include "peer_connection_factory.h"
#include "rtc_peer_connection.h"

namespace python_webrtc {

  void Interfaces::Init(pybind11::module &m) {
    python_webrtc::PeerConnectionFactory::Init(m);
    python_webrtc::RTCPeerConnection::Init(m);
  }
}
