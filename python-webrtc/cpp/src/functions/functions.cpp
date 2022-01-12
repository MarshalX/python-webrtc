//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "functions.h"

#include "get_user_media.cpp"

namespace python_webrtc {

  void Functions::Init(pybind11::module &m) {
    m.def("getUserMedia", &GetUserMedia, pybind11::return_value_policy::move);
  }

}
