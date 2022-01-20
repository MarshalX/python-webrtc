#include <pybind11/pybind11.h>

#include "enums/enums.h"
#include "models/models.h"
#include "interfaces/interfaces.h"
#include "functions/functions.h"

namespace py = pybind11;

static void ping() {
  py::print("pong");
}

PYBIND11_MODULE(wrtc, m) {
  m.def("ping", &ping);

  python_webrtc::Enums::Init(m);
  python_webrtc::Models::Init(m);
  python_webrtc::Interfaces::Init(m);
  python_webrtc::Functions::Init(m);
}
