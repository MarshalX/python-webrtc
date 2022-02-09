//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class SdpType {
  public:
    static void Init(pybind11::module &m);
  };

}
