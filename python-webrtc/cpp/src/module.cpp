#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"

namespace py = pybind11;

static void ping() {
  py::print("pong");
}

PYBIND11_MODULE(webrtc, m) {
  m.def("ping", &ping);

  python_webrtc::PeerConnectionFactory::Init(m);
}
