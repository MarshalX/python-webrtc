//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_GIL_H_
#define PYTHON_WEBRTC_UTILS_GIL_H_

#include <chrono>
#include <thread>
#include <utility>

#include <pybind11/pybind11.h>

#include "dispatcher.h"
#include "parking.h"

namespace python_webrtc {

  class gil_release {
  public:
    gil_release() : _state(PyEval_SaveThread()) {}

    ~gil_release() {
#if PY_VERSION_HEX < 0x030E0000
      // before 3.14, re-attaching after exit runs pthread_exit, whose unwinding through libwebrtc aborts
      {
        const Dispatcher::PythonEntry entry;
        if (entry) {
          PyEval_RestoreThread(_state);
          return;
        }
      }
      Parking::At("gil.exit");
      while (true) {
        std::this_thread::sleep_for(std::chrono::hours(1));
      }
#else
      PyEval_RestoreThread(_state);
#endif
    }

    gil_release(const gil_release &) = delete;
    gil_release &operator=(const gil_release &) = delete;

  private:
    PyThreadState *_state;
  };

  using nogil = pybind11::call_guard<gil_release>;

  // property accessors can't take a call guard
  template <typename F>
  pybind11::cpp_function nogil_fn(F &&function) {
    return pybind11::cpp_function(std::forward<F>(function), nogil());
  }

  // A pybind11::init factory without the GIL: a call guard would also cover registering the instance, which needs it
  template <typename R, typename... Args>
  auto nogil_factory(R (*factory)(Args...)) {
    return [factory](Args... args) {
      const gil_release release;
      return factory(std::forward<Args>(args)...);
    };
  }

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_GIL_H_
