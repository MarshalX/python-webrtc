//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_DISPATCHER_H_
#define PYTHON_WEBRTC_UTILS_DISPATCHER_H_

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <set>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class Dispatcher {
  public:
    static void Destroy(std::function<void()> destroy, int generation);

    static void Wake(uint64_t mailbox);

    static void SetWake(pybind11::function wake);

    static void StopAtExit();

#if PY_VERSION_HEX < 0x030E0000
    class PythonEntry {
    public:
      PythonEntry();
      ~PythonEntry();

      PythonEntry(const PythonEntry &) = delete;
      PythonEntry &operator=(const PythonEntry &) = delete;

      explicit operator bool() const { return _entered; }

    private:
      bool _entered = false;
    };
#endif

    static bool IsCurrent();

    // held across a fork, so the child doesn't get the queue locked by a thread it doesn't have
    static void LockForFork();
    static void UnlockAfterFork();

    static int Threads();

    static void Idle();

    static void Init(pybind11::module &m);

  private:
    Dispatcher();

    static Dispatcher &Instance();

    std::unique_lock<std::mutex> Locked();
    void StartLocked();
    [[noreturn]] void Run();
    void WakeLoops(const std::set<uint64_t> &mailboxes);
    void EnterPython(const std::function<void()> &function);

    std::mutex _mutex;
    std::condition_variable _posted;
    std::condition_variable _idle;
    std::condition_variable _left;
    std::deque<std::function<void()>> _destroys;
    std::set<uint64_t> _wakes;
    int _generation;
    bool _started = false;
    bool _running = false;
    bool _entering = false;
    std::atomic<bool> _exiting{false};
    std::atomic<int> _threads{0};
    std::optional<pybind11::function> _wake;
#if PY_VERSION_HEX >= 0x030F0000
    PyInterpreterView *_view = nullptr;
#endif
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_DISPATCHER_H_
