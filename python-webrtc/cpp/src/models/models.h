//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_MODELS_H_
#define PYTHON_WEBRTC_MODELS_MODELS_H_

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace python_webrtc {

  class Models {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_MODELS_H_
