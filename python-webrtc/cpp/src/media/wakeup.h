//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_WAKEUP_H_
#define PYTHON_WEBRTC_MEDIA_WAKEUP_H_

#include <condition_variable>
#include <deque>
#include <memory>
#include <mutex>
#include <thread>

#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  // What a Wakeup delivers to, on its thread
  class Wakeable {
  public:
    virtual ~Wakeable() = default;

    virtual void OnWakeup() = 0;
  };

  // Wakes Python from a thread of its own, so media threads (decoders, the audio device) never wait for the GIL
  class Wakeup {
  public:
    // from any thread, never blocking on anything but a short lock
    static void Post(std::weak_ptr<Wakeable> target) {
      auto &wakeup = Instance();
      {
        const std::scoped_lock lock(wakeup._mutex);
        if (wakeup._generation != Forks().load()) {
          // the child of a fork: the thread is gone, and so are the objects of the parent
          wakeup._generation = Forks().load();
          wakeup._targets.clear();
          std::thread([&wakeup]() { wakeup.Run(); }).detach();
        }
        wakeup._targets.push_back(std::move(target));
      }
      wakeup._posted.notify_one();
    }

    // held across a fork, so the child doesn't get it locked by a thread it doesn't have
    static void LockForFork() { Instance()._mutex.lock(); }

    static void UnlockAfterFork() { Instance()._mutex.unlock(); }

  private:
    static Wakeup &Instance() {
      // never destroyed: its thread may run while the process exits
      static auto *wakeup = new Wakeup();
      return *wakeup;
    }

    Wakeup() {
      std::thread([this]() { Run(); }).detach();
    }

    [[noreturn]] void Run() {
      while (true) {
        std::weak_ptr<Wakeable> target;
        {
          std::unique_lock<std::mutex> lock(_mutex);
          _posted.wait(lock, [this]() { return !_targets.empty(); });
          target = std::move(_targets.front());
          _targets.pop_front();
        }
        // the last reference may be released here, on this thread
        if (auto locked = target.lock()) {
          locked->OnWakeup();
        }
      }
    }

    std::mutex _mutex;
    // of the process the thread runs in (see forks)
    int _generation = Forks().load();
    std::condition_variable _posted;
    std::deque<std::weak_ptr<Wakeable>> _targets;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_WAKEUP_H_
