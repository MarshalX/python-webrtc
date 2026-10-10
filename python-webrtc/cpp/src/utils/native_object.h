//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_NATIVE_OBJECT_H_
#define PYTHON_WEBRTC_UTILS_NATIVE_OBJECT_H_

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include "dispatcher.h"
#include "libwebrtc_thread.h"

namespace python_webrtc {

  class AliveCounter {
  public:
    explicit AliveCounter(const char *name) {
      const std::scoped_lock lock(Mutex());
      Counters().emplace(name, this);
    }

    AliveCounter(const AliveCounter &) = delete;
    AliveCounter &operator=(const AliveCounter &) = delete;

    static std::map<std::string, int> Counts() {
      const std::scoped_lock lock(Mutex());
      std::map<std::string, int> counts;
      for (const auto &[name, counter] : Counters()) {
        counts[name] = counter->alive.load();
      }
      return counts;
    }

    std::atomic<int> alive{0};

  private:
    // leaked: read until the process ends
    static std::map<std::string, const AliveCounter *> &Counters() {
      static auto *counters = new std::map<std::string, const AliveCounter *>();
      return *counters;
    }

    static std::mutex &Mutex() {
      static ForkLocal<std::mutex> mutex;
      return mutex.Get();
    }
  };

  inline std::map<std::string, int> AliveCounts() {
    return AliveCounter::Counts();
  }

  inline std::atomic<uint64_t> &NextNativeId() {
    static std::atomic<uint64_t> next{1};
    return next;
  }

  template <typename T>
  class NativeObject : public std::enable_shared_from_this<T> {
  public:
    [[nodiscard]] uint64_t Id() const { return _id; }

    static int Alive() { return _counter.alive.load(); }

    template <typename F>
    auto Guard(F task) const {
      return [alive = _alive, task = std::move(task)](auto &&...args) mutable {
        if (*alive) {
          task(std::forward<decltype(args)>(args)...);
        }
      };
    }

    template <typename... Args>
    static std::shared_ptr<T> Create(Args &&...args) {
      return std::shared_ptr<T>(new T(std::forward<Args>(args)...), [generation = Forks().load()](T *dying) {
        Dispatcher::Destroy([dying]() { delete dying; }, generation);
      });
    }

  protected:
    NativeObject() : _id(NextNativeId()++) { _counter.alive++; }

    // runs after T's members: the count holds while T is destroyed
    ~NativeObject() {
#ifdef WRTC_SANITIZED
      // a throwing constructor destroys the half-made object where it was made
      if (std::uncaught_exceptions() == 0 && !Dispatcher::IsCurrent()) {
        (void)std::fprintf(stderr, "python-webrtc: %s destroyed off the Dispatcher, see NativeObject::Create\n",
                           T::kName);
        std::abort();
      }
#endif
      *_alive = false;
      _counter.alive--;
    }

    NativeObject(const NativeObject &) = delete;
    NativeObject &operator=(const NativeObject &) = delete;

    void Disarm() { *_alive = false; }

  private:
    static inline AliveCounter _counter{T::kName};
    const uint64_t _id;
    const std::shared_ptr<std::atomic<bool>> _alive = std::make_shared<std::atomic<bool>>(true);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_NATIVE_OBJECT_H_
