//
// Created by Il'ya Semyonov on 1/5/22.
//

#pragma once

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class Models {
  public:
    static void Init(pybind11::module &m);
  };

}
