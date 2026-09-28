//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <mutex>
#include <optional>

namespace python_webrtc {

  // An attribute that changes when Python delivers its event (Surface), rather than when libwebrtc reports it;
  // without listeners there are no events, and the current value is seen.
  template<typename T>
  class Surfaced {
  public:
    // a change reported by libwebrtc, before its event is emitted
    void Changed(bool listening, T previous) {
      std::lock_guard<std::mutex> lock(_mutex);
      if (!listening) {
        _value.reset();
      } else if (!_value) {
        _value = previous;
      }
    }

    void Surface(T value) {
      std::lock_guard<std::mutex> lock(_mutex);
      _value = value;
    }

    // shows the current value again, like when events stop
    void Reset() {
      std::lock_guard<std::mutex> lock(_mutex);
      _value.reset();
    }

    T Get(T current) {
      std::lock_guard<std::mutex> lock(_mutex);
      return _value ? *_value : current;
    }

  private:
    std::mutex _mutex;
    std::optional<T> _value;
  };

} // namespace python_webrtc
