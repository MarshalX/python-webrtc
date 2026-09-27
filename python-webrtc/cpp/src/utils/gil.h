//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <utility>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Calls into libwebrtc block on its internal threads, which may themselves need the GIL
  // (to run or release Python callbacks), so every native call has to release it first.
  using nogil = pybind11::call_guard<pybind11::gil_scoped_release>;

  // Property getters/setters can't take a call guard directly, wrap them into a function instead.
  // Keeps the default policy of properties: pybind11 applies it only to getters it wraps itself,
  // and returned pointers are owned by the C++ side, never by Python.
  template<typename F>
  pybind11::cpp_function nogil_fn(F &&f) {
    return pybind11::cpp_function(std::forward<F>(f), pybind11::return_value_policy::reference_internal, nogil());
  }

} // namespace python_webrtc
