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

  // Tasks a wrapper posts to a libwebrtc thread (like registering itself as an observer from its constructor) that
  // don't run once the wrapper is destroyed.
  //
  // A destructor running on another thread waits for the posted task with a blocking call to the same thread, but
  // one running on that thread (when libwebrtc callbacks drop the last reference) runs its blocking call inline,
  // before the task: the task then finds the guard gone. Tasks and destructors never overlap, as they either run
  // on the same thread or the destructor waits for that thread.
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
