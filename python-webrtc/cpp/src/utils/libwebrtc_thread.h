//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <cstdio>
#include <cstdlib>
#include <memory>
#include <thread>
#include <utility>

#include "gil.h"

namespace python_webrtc {

  // Whether this is a libwebrtc thread. Python code runs on them (to emit events), and so does the garbage collector,
  // which may release the last reference to a wrapper, whose destructor blocks on libwebrtc threads that may be
  // blocked on this one.
  inline thread_local bool onLibwebrtcThread = false;

  // Marks the calling thread as a libwebrtc one while it runs Python code
  class LibwebrtcThreadScope {
  public:
    LibwebrtcThreadScope() : _previous(onLibwebrtcThread) {
      onLibwebrtcThread = true;
    }

    ~LibwebrtcThreadScope() {
      onLibwebrtcThread = _previous;
    }

    LibwebrtcThreadScope(const LibwebrtcThreadScope &) = delete;
    LibwebrtcThreadScope &operator=(const LibwebrtcThreadScope &) = delete;

  private:
    bool _previous;
  };

  // Runs a release right away, or on a thread of its own on a libwebrtc thread
  template<typename F>
  void ReleaseOffLibwebrtcThread(F &&release) {
    if (onLibwebrtcThread) {
      std::thread(std::forward<F>(release)).detach();
    } else {
      release();
    }
  }

  // Deletes wrappers whose destructors block on libwebrtc threads off those threads
  struct DeleteOffLibwebrtcThread {
    template<typename T>
    void operator()(T *dying) const {
      ReleaseOffLibwebrtcThread([dying]() { delete dying; });
    }
  };

  // Starts a destructor that blocks on libwebrtc threads: releases the GIL, and aborts on a libwebrtc thread, where
  // it may deadlock (a wrapper owned without DeleteOffLibwebrtcThread)
  class BlockingDestructor {
  public:
    explicit BlockingDestructor(const char *name) {
      if (onLibwebrtcThread) {
        std::fprintf(stderr, "python-webrtc: %s destroyed on a libwebrtc thread, see DeleteOffLibwebrtcThread\n", name);
        std::abort();
      }
    }

  private:
    gil_release_if_held _release;
  };

} // namespace python_webrtc
