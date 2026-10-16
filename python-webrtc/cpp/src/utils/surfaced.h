//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_SURFACED_H_
#define PYTHON_WEBRTC_UTILS_SURFACED_H_

#include <mutex>
#include <optional>
#include <utility>

namespace python_webrtc {

  // An attribute that changes when Python delivers its event (Surface), rather than when libwebrtc reports it;
  // unbound, there are no events, and the current value is seen.
  template <typename T>
  class Surfaced {
  public:
    // a change reported by libwebrtc, before its event is emitted
    void Changed(bool bound, const T &previous) {
      const std::scoped_lock lock(_mutex);
      if (!bound) {
        _value.reset();
      } else if (!_value) {
        _value = previous;
      }
    }

    void Surface(T value) {
      const std::scoped_lock lock(_mutex);
      _value = std::move(value);
    }

    template <typename F>
    void Update(F update) {
      const std::scoped_lock lock(_mutex);
      if (_value) {
        update(*_value);
      }
    }

    // shows the current value again, like when events stop
    void Reset() {
      const std::scoped_lock lock(_mutex);
      _value.reset();
    }

    T Get(T current) {
      const std::scoped_lock lock(_mutex);
      return _value ? *_value : current;
    }

    T Shown(bool bound, T current) {
      const std::scoped_lock lock(_mutex);
      if (!bound) {
        _value.reset();
        return current;
      }
      return _value ? *_value : current;
    }

    // like Shown, but reads the current value (a call to libwebrtc's thread) only when it's shown
    template <typename Current>
    T ShownOr(bool bound, Current current) {
      {
        const std::scoped_lock lock(_mutex);
        if (bound && _value) {
          return *_value;
        }
        if (!bound) {
          _value.reset();
        }
      }
      return current();
    }

  private:
    std::mutex _mutex;
    std::optional<T> _value;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_SURFACED_H_
