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

namespace python_webrtc {

  // A function another object sets (like the connection of a transport), which may be set on one thread while it's
  // called on another. It's called out of the lock: calls block on libwebrtc threads, which may be setting it.
  template<typename Signature>
  class LockedFunction {
  public:
    void Set(std::function<Signature> function) {
      std::lock_guard<std::mutex> lock(_mutex);
      _function = std::move(function);
    }

    std::function<Signature> Get() {
      std::lock_guard<std::mutex> lock(_mutex);
      return _function;
    }

  private:
    std::mutex _mutex;
    std::function<Signature> _function;
  };

} // namespace python_webrtc
