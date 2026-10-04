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
#include "utils/gil.h"
#include "utils/held_events.h"
#include "utils/python_callback.h"

#include <thread>
#include <utility>

namespace py = pybind11;

namespace {

  void ping() {
    py::print("pong");
  }

  struct Unconvertible {};

  // for tests
  void callbackUnconvertible(py::function callback) {
    auto call = python_webrtc::PythonCallback<Unconvertible>(std::move(callback));
    const python_webrtc::gil_release release;
    std::thread([call]() { call(Unconvertible{}); }).join();
  }

  // for tests
  void heldEventsWithGil() {
    (void)python_webrtc::HeldEvents().IsHeld();
  }

} // namespace

PYBIND11_MODULE(wrtc, m) {
  m.def("ping", &ping);
  m.def("_callback_unconvertible", &callbackUnconvertible);
  m.def("_held_events_with_gil", &heldEventsWithGil);
  py::module_::import("atexit").attr("register")(py::cpp_function([]() {
    python_webrtc::StopEnteringPython();
    python_webrtc::PendingOperations::FailAll();
  }));
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
  python_webrtc::OpenH264::Init(m);
}
