//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <functional>
#include <mutex>
#include <utility>
#include <vector>

namespace python_webrtc {

  // Events emitted while held are kept, and emitted in order on release: an event mustn't come before one that
  // it follows, like the candidates a local description starts gathering before the description is set
  class HeldEvents {
  public:
    void Hold() {
      std::lock_guard<std::mutex> lock(_mutex);
      _held = true;
    }

    void Release() {
      std::lock_guard<std::mutex> lock(_mutex);
      // emitted under the lock, so that events emitted meanwhile come after these
      for (auto &emit: _events) {
        emit();
      }
      _events.clear();
      _held = false;
    }

    bool IsHeld() {
      std::lock_guard<std::mutex> lock(_mutex);
      return _held;
    }

    // emits an event now, or on release while held
    template<typename F>
    void Emit(F &&emit) {
      {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_held) {
          _events.emplace_back(std::forward<F>(emit));
          return;
        }
      }
      emit();
    }

  private:
    std::mutex _mutex;
    bool _held = false;
    std::vector<std::function<void()>> _events;
  };

} // namespace python_webrtc
