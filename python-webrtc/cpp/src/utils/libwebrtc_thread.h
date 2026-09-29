//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_
#define PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include "gil.h"

namespace python_webrtc {

  // Whether this is a libwebrtc thread. Python code runs on them (to emit events), and so does the garbage collector,
  // which may release the last reference to a wrapper, whose destructor blocks on libwebrtc threads that may be
  // blocked on this one.
  inline bool &OnLibwebrtcThread() {
    static thread_local bool onLibwebrtcThread = false;
    return onLibwebrtcThread;
  }

  // Marks the calling thread as a libwebrtc one while it runs Python code
  class LibwebrtcThreadScope {
  public:
    LibwebrtcThreadScope() : _previous(OnLibwebrtcThread()) { OnLibwebrtcThread() = true; }

    ~LibwebrtcThreadScope() { OnLibwebrtcThread() = _previous; }

    LibwebrtcThreadScope(const LibwebrtcThreadScope &) = delete;
    LibwebrtcThreadScope &operator=(const LibwebrtcThreadScope &) = delete;

  private:
    bool _previous;
  };

  // Forks, counted in the child: objects from before one are never released there, their threads are gone
  inline std::atomic<int> &Forks() {
    static std::atomic<int> forks{0};
    return forks;
  }

  // Runs a release right away, or on a thread of its own on a libwebrtc thread; leaks while the interpreter finalizes
  template <typename F>
  void ReleaseOffLibwebrtcThread(F &&release, int generation = Forks().load()) {
    if (!PythonAlive() || generation != Forks().load()) {
      return;
    }
    if (OnLibwebrtcThread()) {
      std::thread(std::forward<F>(release)).detach();
    } else {
      release();
    }
  }

  // Deletes wrappers whose destructors block on libwebrtc threads off those threads
  struct DeleteOffLibwebrtcThread {
    // of the process the wrapper was created in (see forks)
    int generation = Forks().load();

    template <typename T>
    void operator()(T *dying) const {
      ReleaseOffLibwebrtcThread(
          [dying]() {
            // members too are released without it, like proxies destroyed on their thread
            const gil_release_if_held release;
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
      if (OnLibwebrtcThread()) {
        const std::string message =
            std::string("python-webrtc: ") + name + " destroyed on a libwebrtc thread, see DeleteOffLibwebrtcThread\n";
        (void)std::fputs(message.c_str(), stderr);
        std::abort();
      }
    }

  private:
    gil_release_if_held _release;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_
