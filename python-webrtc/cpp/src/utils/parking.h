//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_PARKING_H_
#define PYTHON_WEBRTC_UTILS_PARKING_H_

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <map>
#include <mutex>
#include <string>

namespace python_webrtc {

  // test-only points where native threads park (wrtc._testing.park); free when none is held
  class Parking {
  public:
    static void At(const char *name) {
      if (Held().load(std::memory_order_acquire) == 0) {
        return;
      }
      auto &state = State();
      std::unique_lock<std::mutex> lock(state.mutex);
      auto it = state.points.find(name);
      if (it == state.points.end() || !it->second.held) {
        return;
      }
      auto &point = it->second;
      point.parked++;
      state.changed.notify_all();
      state.changed.wait(lock, [&point]() { return !point.held; });
      point.parked--;
    }

    static void Park(const std::string &name) {
      auto &state = State();
      const std::scoped_lock lock(state.mutex);
      auto &point = state.points[name];
      if (!point.held) {
        point.held = true;
        Held()++;
      }
    }

    static void Release(const std::string &name) {
      auto &state = State();
      {
        const std::scoped_lock lock(state.mutex);
        auto &point = state.points[name];
        if (!point.held) {
          return;
        }
        point.held = false;
        Held()--;
      }
      state.changed.notify_all();
    }

    static bool Parked(const std::string &name, double timeout) {
      auto &state = State();
      std::unique_lock<std::mutex> lock(state.mutex);
      auto &point = state.points[name];
      return state.changed.wait_for(lock, std::chrono::duration<double>(timeout),
                                    [&point]() { return point.parked > 0; });
    }

  private:
    struct Point {
      bool held = false;
      int parked = 0;
    };

    struct Points {
      std::mutex mutex;
      std::condition_variable changed;
      std::map<std::string, Point> points;
    };

    static std::atomic<int> &Held() {
      static std::atomic<int> held{0};
      return held;
    }

    static Points &State() {
      // leaked: a parked thread may outlive static destructors
      static auto *state = new Points();
      return *state;
    }
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_PARKING_H_
