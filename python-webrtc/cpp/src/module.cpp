//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <pybind11/pybind11.h>

#include "config.h"
#include "enums/enums.h"
#include "models/models.h"
#include "interfaces/interfaces.h"
#include "functions/functions.h"

namespace py = pybind11;

static bool copyrightShowed = false;

static void ping() {
  py::print("pong");
}

PYBIND11_MODULE(wrtc, m) {
  if (!copyrightShowed) {
    auto ver = std::string(PROJECT_VER);
    auto dev = std::count(ver.begin(), ver.end(), '.') == 3 ? " DEV" : "";
    py::print("Python WebRTC v" + ver + dev + ", Copyright (C) 2022 Il`ya (Marshal) <https://github.com/MarshalX>");
    py::print("Licensed under the terms of the BSD 3-Clause License\n\n");

    copyrightShowed = true;
  }

  m.def("ping", &ping);

  python_webrtc::Enums::Init(m);
  python_webrtc::Models::Init(m);
  python_webrtc::Interfaces::Init(m);
  python_webrtc::Functions::Init(m);
}
