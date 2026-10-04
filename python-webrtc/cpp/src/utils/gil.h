//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_GIL_H_
#define PYTHON_WEBRTC_UTILS_GIL_H_

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <optional>
#include <thread>
#include <utility>

#include <pybind11/pybind11.h>

#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__)
#define WRTC_SANITIZED
#elif defined(__has_feature)
#if __has_feature(address_sanitizer) || __has_feature(thread_sanitizer)
#define WRTC_SANITIZED
#endif
#endif

namespace python_webrtc {

  // Once the interpreter finalizes, another thread taking the GIL is stopped: with pthread_exit before 3.14, whose
  // unwinding through native frames (noexcept ones, libwebrtc's) aborts. So threads stop taking it at exit already.
  inline std::atomic<bool> &PythonExiting() {
    static std::atomic<bool> exiting{false};
    return exiting;
  }
  // the thread running the exit, which finalizes the interpreter
  inline std::atomic<std::thread::id> &ExitThread() {
    static std::atomic<std::thread::id> thread{};
    return thread;
  }
  // threads entering Python or taking the GIL back, which the exit waits for
  inline std::atomic<int> &PythonEntries() {
    static std::atomic<int> entries{0};
    return entries;
  }

  // Whether Python code can still run: libwebrtc threads may outlive the interpreter
  inline bool PythonAlive() {
    if (PythonExiting()) {
      return false;
    }
#if PY_VERSION_HEX >= 0x030D0000
    return (Py_IsInitialized() != 0) && (Py_IsFinalizing() == 0);
#else
    return Py_IsInitialized() && !_Py_IsFinalizing();
#endif
  }

  // Taking the GIL from a thread without it: not once the interpreter exits (see pythonExiting)
  class PythonEntry {
  public:
    PythonEntry() : _entered(Enter()) {}

    ~PythonEntry() { PythonEntries()--; }

    PythonEntry(const PythonEntry &) = delete;
    PythonEntry &operator=(const PythonEntry &) = delete;

    explicit operator bool() const { return _entered; }

  private:
    // counted before checking, so the exit either sees the entry or the entry sees the exit
    static bool Enter() {
      PythonEntries()++;
      return PythonAlive();
    }

    bool _entered;
  };

  // Releases the GIL, like pybind11::gil_scoped_release. Once the interpreter exits, other threads than the exiting
  // one (daemon threads) wait for the process to end rather than take it back, as in 3.14.
  class gil_release {
  public:
    gil_release() : _state(PyEval_SaveThread()) {}

    ~gil_release() {
      {
        const PythonEntry entry;
        if (entry || std::this_thread::get_id() == ExitThread()) {
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
    ExitThread() = std::this_thread::get_id();
    PythonExiting() = true;
    const gil_release release;
    // bounded: a Python handler may never return
    constexpr auto timeout = std::chrono::seconds(5);
    auto deadline = std::chrono::steady_clock::now() + timeout;
    while (PythonEntries() > 0 && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  // Calls into libwebrtc block on its internal threads, which may themselves need the GIL
  // (to run or release Python callbacks), so every native call has to release it first.
  using nogil = pybind11::call_guard<gil_release>;

  // Property getters/setters can't take a call guard directly, wrap them into a function instead.
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

  // Destructors of wrappers block on libwebrtc threads (to unregister observers, to stop threads),
  // which may be waiting for the GIL. They can run on any thread, with or without the GIL held.
  class gil_release_if_held {
  public:
    gil_release_if_held() {
      if ((Py_IsInitialized() != 0) && (PyGILState_Check() != 0)) {
        _release.emplace();
      }
    }

  private:
    std::optional<gil_release> _release;
  };

  // sanitizer builds: the GIL must not be held here (lock-before-GIL order)
  inline void CheckGilNotHeld([[maybe_unused]] const char *where) {
#ifdef WRTC_SANITIZED
    if ((Py_IsInitialized() != 0) && (PyGILState_Check() != 0)) {
      (void)std::fprintf(stderr, "python-webrtc: %s called with the GIL held, which can deadlock\n", where);
      std::abort();
    }
#endif
  }

  // Reports any exception as unraisable
  template <typename F>
  void CallUnraisable(const char *context, F &&call) {
    try {
      std::forward<F>(call)();
    } catch (pybind11::error_already_set &e) {
      e.discard_as_unraisable(context);
    } catch (const std::exception &e) {
      PyErr_SetString(PyExc_RuntimeError, e.what());
      pybind11::error_already_set().discard_as_unraisable(context);
    }
  }

  // Releases a Python object on any thread, from destructors too: leaked once the interpreter is gone, or if
  // pybind11 fails to take the GIL, which is reported rather than terminating
  inline void ReleasePythonObject(pybind11::object &object) noexcept {
    const PythonEntry entry;
    if (!entry) {
      // the interpreter is gone, and so are the objects
      (void)object.release();
      return;
    }
    if (!object) {
      return;
    }
    try {
      const pybind11::gil_scoped_acquire gil;
      const pybind11::object dropped = std::move(object);
    } catch (const std::exception &e) {
      (void)object.release();
      (void)std::fputs("python-webrtc: leaked a Python object, the GIL couldn't be taken: ", stderr);
      (void)std::fputs(e.what(), stderr);
      (void)std::fputs("\n", stderr);
    }
  }

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_GIL_H_
