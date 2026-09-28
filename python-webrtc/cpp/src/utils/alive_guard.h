//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>
#include <utility>

namespace python_webrtc {

  // Tasks a wrapper posts to a libwebrtc thread (like its observer registration: it's created under locks the
  // signaling thread may wait for) that don't run once the wrapper is destroyed. Destructors run on the task's
  // thread or block on it, so a task never overlaps a destructor.
  class AliveGuard {
  public:
    ~AliveGuard() {
      *_alive = false;
    }

    template<typename F>
    auto Guard(F task) {
      return [alive = _alive, task = std::move(task)]() mutable {
        if (*alive) {
          task();
        }
      };
    }

  private:
    std::shared_ptr<std::atomic<bool>> _alive = std::make_shared<std::atomic<bool>>(true);
  };

} // namespace python_webrtc
