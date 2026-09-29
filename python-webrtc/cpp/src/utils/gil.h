//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <chrono>
#include <optional>
#include <thread>
#include <utility>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Once the interpreter finalizes, another thread taking the GIL is stopped: with pthread_exit before 3.14, whose
  // unwinding through native frames (noexcept ones, libwebrtc's) aborts. So threads stop taking it at exit already.
  inline std::atomic<bool> pythonExiting{false};
  // the thread running the exit, which finalizes the interpreter
  inline std::atomic<std::thread::id> exitThread{};
  // threads entering Python or taking the GIL back, which the exit waits for
  inline std::atomic<int> pythonEntries{0};

  // Whether Python code can still run: libwebrtc threads may outlive the interpreter
  inline bool PythonAlive() {
    if (pythonExiting) {
      return false;
    }
#if PY_VERSION_HEX >= 0x030D0000
    return Py_IsInitialized() && !Py_IsFinalizing();
#else
    return Py_IsInitialized() && !_Py_IsFinalizing();
#endif
  }

  // Taking the GIL from a thread without it: not once the interpreter exits (see pythonExiting)
  class PythonEntry {
  public:
    PythonEntry() {
      pythonEntries++;
      _entered = PythonAlive();
    }

    ~PythonEntry() {
      pythonEntries--;
    }

    PythonEntry(const PythonEntry &) = delete;
    PythonEntry &operator=(const PythonEntry &) = delete;

    explicit operator bool() const {
      return _entered;
    }

  private:
    bool _entered;
  };

  // Releases the GIL, like pybind11::gil_scoped_release. Once the interpreter exits, other threads than the exiting
  // one (daemon threads) wait for the process to end rather than take it back, as in 3.14.
  class gil_release {
  public:
    gil_release() : _state(PyEval_SaveThread()) {}

    ~gil_release() {
      {
        PythonEntry entry;
        if (entry || std::this_thread::get_id() == exitThread) {
          PyEval_RestoreThread(_state);
          return;
        }
      }
      while (true) {
        std::this_thread::sleep_for(std::chrono::hours(1));
      }
    }

    gil_release(const gil_release &) = delete;
    gil_release &operator=(const gil_release &) = delete;

  private:
    PyThreadState *_state;
  };

  // An atexit handler: threads stop taking the GIL before the interpreter finalizes, the ones taking it are waited for
  inline void StopEnteringPython() {
    exitThread = std::this_thread::get_id();
    pythonExiting = true;
    gil_release release;
    // bounded: a Python handler may never return
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (pythonEntries > 0 && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  // Calls into libwebrtc block on its internal threads, which may themselves need the GIL
  // (to run or release Python callbacks), so every native call has to release it first.
  using nogil = pybind11::call_guard<gil_release>;

  // Property getters/setters can't take a call guard directly, wrap them into a function instead.
  template<typename F>
  pybind11::cpp_function nogil_fn(F &&f) {
    return pybind11::cpp_function(std::forward<F>(f), nogil());
  }

  // A pybind11::init factory without the GIL: a call guard would also cover registering the instance, which needs it
  template<typename R, typename... Args>
  auto nogil_factory(R (*factory)(Args...)) {
    return [factory](Args... args) {
      gil_release release;
      return factory(std::forward<Args>(args)...);
    };
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
    std::optional<gil_release> _release;
  };

} // namespace python_webrtc
