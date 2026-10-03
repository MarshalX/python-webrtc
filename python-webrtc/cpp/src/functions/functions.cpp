//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "functions.h"
#include "../utils/gil.h"
#include "get_user_media.h"

namespace python_webrtc {

  void Functions::Init(pybind11::module &m) {
    // the defaults are Python's (webrtc.get_user_media)
    m.def("getUserMedia", &GetUserMedia, nogil(), pybind11::arg("audio"), pybind11::arg("video"),
          pybind11::arg("width"), pybind11::arg("height"), pybind11::arg("frameRate"));
  }

} // namespace python_webrtc
