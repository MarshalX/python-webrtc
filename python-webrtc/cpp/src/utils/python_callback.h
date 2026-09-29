//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_
#define PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_

#include <functional>
#include <memory>
#include <utility>

#include <pybind11/pybind11.h>

#include "../exceptions.h"
#include "gil.h"

namespace python_webrtc {

  // A Python function called back from libwebrtc threads. pybind11's std::function takes the GIL to be called, copied
  // or released, which stops the thread once the interpreter exits: this one is ignored then (see PythonEntry).
  template <typename... Args>
  std::function<void(Args...)> PythonCallback(pybind11::function function) {
    const std::shared_ptr<pybind11::function> held(new pybind11::function(std::move(function)),
                                                   [](pybind11::function *function) {
                                                     const PythonEntry entry;
                                                     if (!entry) {
                                                       // the interpreter is gone
                                                       (void)function->release();
                                                       delete function;
                                                       return;
                                                     }
                                                     const pybind11::gil_scoped_acquire gil;
                                                     delete function;
                                                   });
    return [held](const Args &...args) {
      const PythonEntry entry;
      if (!entry) {
        return;
      }
      const pybind11::gil_scoped_acquire gil;
      try {
        (*held)(args...);
      } catch (pybind11::error_already_set &e) {
        e.discard_as_unraisable("callback");
      }
    };
  }

  // A method taking (onSuccess, onFailure, ...) callbacks, bound with PythonCallbacks and without the GIL
  template <typename C, typename... Result, typename... Rest>
  auto WithCallbacks(void (C::*method)(std::function<void(Result...)> &, std::function<void(RTCCallbackException)> &,
                                       Rest...)) {
    return [method](C &self, pybind11::function onSuccess, pybind11::function onFailure, Rest... rest) {
      auto success = PythonCallback<Result...>(std::move(onSuccess));
      auto failure = PythonCallback<RTCCallbackException>(std::move(onFailure));
      const gil_release release;
      (self.*method)(success, failure, std::forward<Rest>(rest)...);
    };
  }

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_
