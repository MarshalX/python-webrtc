//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "functions.h"
#include "../utils/gil.h"

#include "get_user_media.cpp"

namespace python_webrtc {

  void Functions::Init(pybind11::module &m) {
    m.def("getUserMedia", &GetUserMedia, nogil(),
          pybind11::arg("audio") = true, pybind11::arg("video") = false, pybind11::arg("width") = 640,
          pybind11::arg("height") = 480, pybind11::arg("frameRate") = 30.0);
  }

}
