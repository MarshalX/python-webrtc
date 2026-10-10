//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <pybind11/pybind11.h>

#include "codecs/openh264.h"
#include "exceptions.h"
#include "functions/functions.h"
#include "interfaces/interfaces.h"
#include "media/media.h"
#include "models/models.h"
#include "testing.h"
#include "utils/dispatcher.h"
#include "utils/libwebrtc_thread.h"
#include "utils/mailbox.h"

namespace py = pybind11;

namespace {

  void ping() {
    py::print("pong");
  }

} // namespace

PYBIND11_MODULE(wrtc, m, pybind11::mod_gil_not_used()) {
  m.def("ping", &ping);
  py::module_::import("atexit").attr("register")(py::cpp_function(&python_webrtc::Dispatcher::StopAtExit));
  // the memory of ASan (its quarantine) and TSan (its shadow) makes resident memory say nothing about leaks
#ifdef WRTC_SANITIZED
  m.attr("_sanitized") = true;
#else
  m.attr("_sanitized") = false;
#endif
  // ThreadSanitizer ends a forked child that starts a thread: tests forking with the Dispatcher running skip
#ifdef WRTC_THREAD_SANITIZED
  m.attr("_thread_sanitized") = true;
#else
  m.attr("_thread_sanitized") = false;
#endif

  python_webrtc::Exceptions::Init(m);
  python_webrtc::Dispatcher::Init(m);
  python_webrtc::Mailbox::Init(m);
  python_webrtc::Models::Init(m);
  python_webrtc::Interfaces::Init(m);
  python_webrtc::Functions::Init(m);
  python_webrtc::Media::Init(m);
  python_webrtc::OpenH264::Init(m);
  python_webrtc::Testing::Init(m);
}
