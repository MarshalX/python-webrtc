//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>

namespace python_webrtc {

  // Counts the live objects of a type, a member of it, so tests can check that none leaks (wrtc._alive)
  template<typename T>
  class AliveCount {
  public:
    AliveCount() {
      count++;
    }

    AliveCount(const AliveCount &) {
      count++;
    }

    AliveCount &operator=(const AliveCount &) = default;

    ~AliveCount() {
      count--;
    }

    static inline std::atomic<int> count{0};
  };

} // namespace python_webrtc
