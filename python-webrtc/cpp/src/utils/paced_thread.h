//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_PACED_THREAD_H_
#define PYTHON_WEBRTC_UTILS_PACED_THREAD_H_

#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>

namespace python_webrtc {

  // A thread calling a function at a steady pace (the synthetic microphone and camera), stopped when destroyed.
  // The function runs on the thread only, so it may keep its state in its captures.
  class PacedThread {
  public:
    ~PacedThread() {
      {
        const std::scoped_lock lock(_mutex);
        _stopping = true;
      }
      _stop.notify_all();
      if (_thread.joinable()) {
        _thread.join();
      }
    }

    PacedThread() = default;

    PacedThread(const PacedThread &) = delete;
    PacedThread &operator=(const PacedThread &) = delete;

    // the first call is right away
    void Start(std::chrono::microseconds interval, std::function<void()> tick) {
      _thread = std::thread([this, interval, tick = std::move(tick)]() {
        auto next = std::chrono::steady_clock::now();
        while (true) {
          {
            std::unique_lock<std::mutex> lock(_mutex);
            if (_stop.wait_until(lock, next, [this]() { return _stopping; })) {
              return;
            }
          }
          next += interval;
          tick();
        }
      });
    }

  private:
    std::mutex _mutex;
    std::condition_variable _stop;
    bool _stopping = false;
    std::thread _thread;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_PACED_THREAD_H_
