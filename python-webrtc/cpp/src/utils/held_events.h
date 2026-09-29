//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_HELD_EVENTS_H_
#define PYTHON_WEBRTC_UTILS_HELD_EVENTS_H_

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
      const std::scoped_lock lock(_mutex);
      _held = true;
    }

    void Release() {
      const std::scoped_lock lock(_mutex);
      // emitted under the lock, so that events emitted meanwhile come after these
      for (auto &emit : _events) {
        emit();
      }
      _events.clear();
      _held = false;
    }

    bool IsHeld() {
      const std::scoped_lock lock(_mutex);
      return _held;
    }

    // emits an event now, or on release while held
    template <typename F>
    void Emit(F &&emit) {
      {
        const std::scoped_lock lock(_mutex);
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

#endif // PYTHON_WEBRTC_UTILS_HELD_EVENTS_H_
