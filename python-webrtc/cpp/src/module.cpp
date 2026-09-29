//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <pybind11/pybind11.h>

#include "config.h"
#include "utils/gil.h"
#include "exceptions.h"
#include "models/models.h"
#include "interfaces/interfaces.h"
#include "functions/functions.h"
#include "media/media.h"

namespace py = pybind11;

#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__)
#define WRTC_SANITIZED
#elif defined(__has_feature)
#if __has_feature(address_sanitizer) || __has_feature(thread_sanitizer)
#define WRTC_SANITIZED
#endif
#endif

static bool copyrightShowed = false;

static void ping() {
  py::print("pong");
}

PYBIND11_MODULE(wrtc, m) {
  if (!copyrightShowed) {
    auto ver = std::string(PROJECT_VER);
    auto dev = ver.find("dev") != std::string::npos ? " DEV" : "";
    py::print("Python WebRTC v" + ver + dev + ", Copyright (C) 2026 Ilya (Marshal) <https://github.com/MarshalX>");
    py::print("Licensed under the terms of the BSD 3-Clause License\n\n");

    copyrightShowed = true;
  }

  m.def("ping", &ping);
  py::module_::import("atexit").attr("register")(py::cpp_function(&python_webrtc::StopEnteringPython));
  // the memory of ASan (its quarantine) and TSan (its shadow) makes resident memory say nothing about leaks
#ifdef WRTC_SANITIZED
  m.attr("_sanitized") = true;
#else
  m.attr("_sanitized") = false;
#endif

  python_webrtc::Exceptions::Init(m);
  python_webrtc::Models::Init(m);
  python_webrtc::Interfaces::Init(m);
  python_webrtc::Functions::Init(m);
  python_webrtc::Media::Init(m);
}
