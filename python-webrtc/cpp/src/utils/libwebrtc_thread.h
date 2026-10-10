//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_
#define PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <utility>

#include <pybind11/pybind11.h>

#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__)
#define WRTC_SANITIZED
#elif defined(__has_feature)
#if __has_feature(address_sanitizer) || __has_feature(thread_sanitizer)
#define WRTC_SANITIZED
#endif
#endif
#ifdef __SANITIZE_THREAD__
#define WRTC_THREAD_SANITIZED
#elif defined(__has_feature)
#if __has_feature(thread_sanitizer)
#define WRTC_THREAD_SANITIZED
#endif
#endif

namespace python_webrtc {

  inline int &HeldTrackedLocks() {
    static thread_local int held = 0;
    return held;
  }

  // for mutexes libwebrtc threads take (see BlockingCallOn)
  template <typename M>
  class TrackedLock {
  public:
    explicit TrackedLock(M &mutex) : _lock(mutex) { HeldTrackedLocks()++; }

    ~TrackedLock() { HeldTrackedLocks()--; }

    TrackedLock(const TrackedLock &) = delete;
    TrackedLock &operator=(const TrackedLock &) = delete;

  private:
    std::scoped_lock<M> _lock;
  };

#ifdef WRTC_SANITIZED
  inline bool AttachedToPython() {
    return (Py_IsInitialized() != 0) && (PyGILState_Check() != 0);
  }

  inline bool &OnNativeThread() {
    static thread_local bool tagged = false;
    return tagged;
  }

  inline void TagNativeThread() {
    OnNativeThread() = true;
  }

  inline void CheckNativeThreadDetached(const char *where) {
    if (OnNativeThread() && AttachedToPython()) {
      (void)std::fprintf(stderr, "python-webrtc: a native thread is attached to Python at %s\n", where);
      std::abort();
    }
  }
#else
  inline void TagNativeThread() {}

  inline void CheckNativeThreadDetached(const char * /*where*/) {}
#endif

  template <typename Thread, typename F>
  decltype(auto) BlockingCallOn(const Thread &thread, F &&function) {
    if (HeldTrackedLocks() > 0 && !thread->IsCurrent()) {
      (void)std::fputs("python-webrtc: blocking on a libwebrtc thread while holding a TrackedLock\n", stderr);
      std::abort();
    }
#ifdef WRTC_SANITIZED
    if (AttachedToPython()) {
      (void)std::fputs("python-webrtc: blocking on a libwebrtc thread while attached to Python\n", stderr);
      std::abort();
    }
#endif
    return thread->BlockingCall(std::forward<F>(function));
  }

  inline std::atomic<int> &Forks() {
    static std::atomic<int> forks{0};
    return forks;
  }

  template <typename T>
  class ForkLocal {
  public:
    T &Get() {
      Holder *holder = _holder.load(std::memory_order_acquire);
      const int forks = Forks().load();
      if (holder == nullptr || holder->generation != forks) {
        auto *fresh = new Holder{forks};
        if (_holder.compare_exchange_strong(holder, fresh)) {
          holder = fresh;
        } else {
          delete fresh;
        }
      }
      return holder->instance;
    }

  private:
    struct Holder {
      int generation;
      T instance;
    };

    std::atomic<Holder *> _holder{nullptr};
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_LIBWEBRTC_THREAD_H_
