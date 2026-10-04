//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_
#define PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_

#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
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

  // for tests
  inline std::atomic<int> &ReleaseThreads() {
    static std::atomic<int> threads{0};
    return threads;
  }

  // One thread releasing what libwebrtc threads can't (they'd block on themselves)
  class ReleaseThread {
  public:
    static void Post(std::function<void()> release, int generation = Forks().load()) {
      auto &thread = Instance();
      {
        const std::scoped_lock lock(thread._mutex);
        if (thread._generation != Forks().load()) {
          // forked child: thread gone, parent's releases leaked
          thread._generation = Forks().load();
          (void)new std::deque<Release>(std::move(thread._releases));
          thread._releases.clear();
          thread._started = false;
        }
        if (!thread._started) {
          thread._started = true;
          ReleaseThreads()++;
          std::thread([&thread]() { thread.Run(); }).detach();
        }
        thread._releases.push_back({std::move(release), generation});
      }
      thread._posted.notify_one();
    }

    static void LockForFork() { Instance()._mutex.lock(); }

    static void UnlockAfterFork() { Instance()._mutex.unlock(); }

  private:
    struct Release {
      std::function<void()> release;
      int generation;
    };

    static ReleaseThread &Instance() {
      // leaked: its thread may outlive exit
      static auto *thread = new ReleaseThread();
      return *thread;
    }

    [[noreturn]] void Run() {
      while (true) {
        Release next;
        {
          std::unique_lock<std::mutex> lock(_mutex);
          _posted.wait(lock, [this]() { return !_releases.empty(); });
          next = std::move(_releases.front());
          _releases.pop_front();
        }
        if (!PythonAlive() || next.generation != Forks().load()) {
          (void)new std::function<void()>(std::move(next.release));
          continue;
        }
        next.release();
      }
    }

    std::mutex _mutex;
    int _generation = Forks().load();
    bool _started = false;
    std::condition_variable _posted;
    std::deque<Release> _releases;
  };

  // Runs a release right away, or on the release thread on a libwebrtc thread; leaks while the interpreter finalizes
  template <typename F>
  void ReleaseOffLibwebrtcThread(F &&release, int generation = Forks().load()) {
    if (!PythonAlive() || generation != Forks().load()) {
      return;
    }
    if (OnLibwebrtcThread()) {
      ReleaseThread::Post(std::forward<F>(release), generation);
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
