//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "functions.h"

#include "get_user_media.cpp"

namespace python_webrtc {

  void Functions::Init(pybind11::module &m) {
    m.def("getUserMedia", &GetUserMedia, pybind11::return_value_policy::move);
  }

}
