//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <condition_variable>
#include <deque>
#include <memory>
#include <mutex>
#include <thread>

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
        std::lock_guard<std::mutex> lock(wakeup._mutex);
        wakeup._targets.push_back(std::move(target));
      }
      wakeup._posted.notify_one();
    }

  private:
    static Wakeup &Instance() {
      // never destroyed: its thread may run while the process exits
      static auto wakeup = new Wakeup();
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
    std::condition_variable _posted;
    std::deque<std::weak_ptr<Wakeable>> _targets;
  };

} // namespace python_webrtc
