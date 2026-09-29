//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <optional>
#include <utility>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Calls into libwebrtc block on its internal threads, which may themselves need the GIL
  // (to run or release Python callbacks), so every native call has to release it first.
  using nogil = pybind11::call_guard<pybind11::gil_scoped_release>;

  // Property getters/setters can't take a call guard directly, wrap them into a function instead.
  template<typename F>
  pybind11::cpp_function nogil_fn(F &&f) {
    return pybind11::cpp_function(std::forward<F>(f), nogil());
  }

  // A pybind11::init factory without the GIL: a call guard would also cover registering the instance, which needs it
  template<typename R, typename... Args>
  auto nogil_factory(R (*factory)(Args...)) {
    return [factory](Args... args) {
      pybind11::gil_scoped_release release;
      return factory(std::forward<Args>(args)...);
    };
  }

  // Whether Python code can still run: libwebrtc threads may outlive the interpreter
  inline bool PythonAlive() {
#if PY_VERSION_HEX >= 0x030D0000
    return Py_IsInitialized() && !Py_IsFinalizing();
#else
    return Py_IsInitialized() && !_Py_IsFinalizing();
#endif
  }

  // Destructors of wrappers block on libwebrtc threads (to unregister observers, to stop threads),
  // which may be waiting for the GIL. They can run on any thread, with or without the GIL held.
  class gil_release_if_held {
  public:
    gil_release_if_held() {
      if (Py_IsInitialized() && PyGILState_Check()) {
        _release.emplace();
      }
    }

  private:
    std::optional<pybind11::gil_scoped_release> _release;
  };

} // namespace python_webrtc
