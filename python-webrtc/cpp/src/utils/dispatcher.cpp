//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "dispatcher.h"

#include "../exceptions.h"
#include "libwebrtc_thread.h"
#include "parking.h"

#include <chrono>
#include <thread>
#include <utility>

#include <rtc_base/platform_thread_types.h>

namespace python_webrtc {

  namespace {
    bool &Current() {
      static thread_local bool current = false;
      return current;
    }

#if PY_VERSION_HEX < 0x030E0000
    std::atomic<int> &Entries() {
      static std::atomic<int> entries{0};
      return entries;
    }

    std::atomic<std::thread::id> &ExitThread() {
      static std::atomic<std::thread::id> thread{};
      return thread;
    }
#endif
  } // namespace

  Dispatcher::Dispatcher() : _generation(Forks().load()) {}

  Dispatcher &Dispatcher::Instance() {
    static auto *dispatcher = new Dispatcher();
    return *dispatcher;
  }

  std::unique_lock<std::mutex> Dispatcher::Locked() {
    std::unique_lock<std::mutex> lock(_mutex);
    if (_generation != Forks().load()) {
      _generation = Forks().load();
      (void)new std::deque<std::function<void()>>(std::move(_destroys));
      _destroys.clear();
      _wakes.clear();
      _started = _running = _entering = false;
      _threads = 0;
    }
    return lock;
  }

  void Dispatcher::StartLocked() {
    if (_started) {
      return;
    }
    _started = true;
    _threads++;
    std::thread([this]() { Run(); }).detach();
  }

  void Dispatcher::Destroy(std::function<void()> destroy, int generation) {
    auto &dispatcher = Instance();
    {
      const auto lock = dispatcher.Locked();
      if (generation != Forks().load() || dispatcher._exiting) {
        (void)new std::function<void()>(std::move(destroy));
        return;
      }
      dispatcher.StartLocked();
      dispatcher._destroys.push_back(std::move(destroy));
    }
    dispatcher._posted.notify_one();
  }

  void Dispatcher::Wake(uint64_t mailbox) {
    auto &dispatcher = Instance();
    {
      const auto lock = dispatcher.Locked();
      if (dispatcher._exiting) {
        return;
      }
      dispatcher.StartLocked();
      dispatcher._wakes.insert(mailbox);
    }
    dispatcher._posted.notify_one();
  }

  void Dispatcher::SetWake(pybind11::function wake) {
    auto &dispatcher = Instance();
    std::optional<pybind11::function> previous;
    {
      const auto lock = dispatcher.Locked();
      previous.swap(dispatcher._wake);
      dispatcher._wake.emplace(std::move(wake));
#if PY_VERSION_HEX >= 0x030F0000
      if (dispatcher._view == nullptr) {
        dispatcher._view = PyInterpreterView_FromCurrent();
      }
#endif
    }
    // the previous one is released here, with the GIL and outside the lock
  }

  void Dispatcher::StopAtExit() {
    auto &dispatcher = Instance();
#if PY_VERSION_HEX < 0x030E0000
    ExitThread() = std::this_thread::get_id();
#endif
    {
      const auto lock = dispatcher.Locked();
      dispatcher._exiting = true;
    }
    // the wake in progress needs the GIL; bounded since its loop may never let go of it
    PyThreadState *state = PyEval_SaveThread();
    constexpr auto timeout = std::chrono::seconds(5);
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    {
      std::unique_lock<std::mutex> lock(dispatcher._mutex);
      (void)dispatcher._left.wait_until(lock, deadline, [&dispatcher]() { return !dispatcher._entering; });
    }
#if PY_VERSION_HEX < 0x030E0000
    while (Entries() > 0 && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
#endif
    PyEval_RestoreThread(state);
  }

#if PY_VERSION_HEX < 0x030E0000
  Dispatcher::PythonEntry::PythonEntry() {
    // counted before the check: StopAtExit sees the entry or the entry sees the exit
    Entries()++;
    // NOLINTNEXTLINE(cppcoreguidelines-prefer-member-initializer): an initializer would check before counting
    _entered = !Instance()._exiting || std::this_thread::get_id() == ExitThread();
  }

  Dispatcher::PythonEntry::~PythonEntry() {
    Entries()--;
  }
#endif

  bool Dispatcher::IsCurrent() {
    return Current();
  }

  void Dispatcher::LockForFork() {
    Instance()._mutex.lock();
  }

  void Dispatcher::UnlockAfterFork() {
    Instance()._mutex.unlock();
  }

  int Dispatcher::Threads() {
    return Instance()._threads.load();
  }

  void Dispatcher::Idle() {
    auto &dispatcher = Instance();
    auto lock = dispatcher.Locked();
    dispatcher._idle.wait(lock, [&dispatcher]() {
      return dispatcher._wakes.empty() && dispatcher._destroys.empty() && !dispatcher._running;
    });
  }

  void Dispatcher::Run() {
    Current() = true;
    webrtc::SetCurrentThreadName("wrtc-dispatcher");
    while (true) {
      std::set<uint64_t> wakes;
      {
        std::function<void()> destroy;
        {
          std::unique_lock<std::mutex> lock(_mutex);
          _posted.wait(lock, [this]() { return !_wakes.empty() || !_destroys.empty(); });
          wakes.swap(_wakes);
          if (!_destroys.empty()) {
            destroy = std::move(_destroys.front());
            _destroys.pop_front();
          }
          _running = true;
        }
        if (!wakes.empty()) {
          WakeLoops(wakes);
        }
        if (destroy) {
          if (_exiting) {
            (void)new std::function<void()>(std::move(destroy));
          } else {
            destroy();
          }
        }
      }
      {
        const std::scoped_lock lock(_mutex);
        _running = false;
      }
      _idle.notify_all();
    }
  }

  void Dispatcher::WakeLoops(const std::set<uint64_t> &mailboxes) {
    Parking::At("dispatcher.wake");
    {
      const std::scoped_lock lock(_mutex);
      if (!_wake || _exiting) {
        return;
      }
      _entering = true;
    }
    EnterPython([this, &mailboxes]() {
      // copied under the lock: _set_wake may replace it from a Python thread
      pybind11::function wake;
      {
        const std::scoped_lock lock(_mutex);
        wake = *_wake;
      }
      for (const auto mailbox : mailboxes) {
        CallUnraisable("Dispatcher.wake", [&]() { wake(mailbox); });
      }
    });
    {
      const std::scoped_lock lock(_mutex);
      _entering = false;
    }
    _left.notify_all();
  }

  // NOLINTNEXTLINE(readability-convert-member-functions-to-static): uses _view on 3.15
  void Dispatcher::EnterPython(const std::function<void()> &function) {
#if PY_VERSION_HEX >= 0x030F0000
    // PEP 788: fails instead of hanging or ending the thread
    PyThreadStateToken *token = PyThreadState_EnsureFromView(_view);
    if (token == nullptr) {
      return;
    }
    function();
    PyThreadState_Release(token);
#else
    const pybind11::gil_scoped_acquire gil;
    function();
#endif
  }

  void Dispatcher::Init(pybind11::module &m) {
    m.def("_set_wake", &Dispatcher::SetWake, pybind11::arg("wake"));
  }

} // namespace python_webrtc
