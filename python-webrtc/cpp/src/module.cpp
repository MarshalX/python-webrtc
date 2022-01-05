#include <pybind11/pybind11.h>

// TODO move to "interfaces" subdir
#include "peer_connection_factory.h"
#include "rtc_peer_connection.h"
#include "enums/enums.h"

namespace py = pybind11;

static void ping() {
  py::print("pong");
}

PYBIND11_MODULE(webrtc, m) {
  m.def("ping", &ping);

  python_webrtc::Enums::Init(m);

  // TODO
  // python_webrtc::Interfaces::Init(m);
  python_webrtc::PeerConnectionFactory::Init(m);
  python_webrtc::RTCPeerConnection::Init(m);
}
