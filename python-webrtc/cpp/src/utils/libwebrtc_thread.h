//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
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

  // Forks, counted in the child: objects from before one are never released there, their threads are gone
  inline std::atomic<int> forks{0};

  // Runs a release right away, or on a thread of its own on a libwebrtc thread; leaks while the interpreter finalizes
  template<typename F>
  void ReleaseOffLibwebrtcThread(F &&release, int generation = forks.load()) {
    if (!PythonAlive() || generation != forks.load()) {
      return;
    }
    if (onLibwebrtcThread) {
      std::thread(std::forward<F>(release)).detach();
    } else {
      release();
    }
  }

  // Deletes wrappers whose destructors block on libwebrtc threads off those threads
  struct DeleteOffLibwebrtcThread {
    // of the process the wrapper was created in (see forks)
    int generation = forks.load();

    template<typename T>
    void operator()(T *dying) const {
      ReleaseOffLibwebrtcThread(
          [dying]() {
            // members too are released without it, like proxies destroyed on their thread
            gil_release_if_held release;
            delete dying;
          },
          generation);
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
