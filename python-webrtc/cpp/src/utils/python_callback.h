//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_
#define PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>

#include <pybind11/pybind11.h>

#include "../exceptions.h"
#include "gil.h"

namespace python_webrtc {

  // Released on any thread, leaked once the interpreter is gone
  inline std::shared_ptr<pybind11::function> HeldFunction(pybind11::function function) {
    return {new pybind11::function(std::move(function)), [](pybind11::function *function) {
              const PythonEntry entry;
              if (!entry) {
                // the interpreter is gone
                (void)function->release();
                delete function;
                return;
              }
              const pybind11::gil_scoped_acquire gil;
              delete function;
            }};
  }

  // A Python function called back from libwebrtc threads. pybind11's std::function takes the GIL to be called, copied
  // or released, which stops the thread once the interpreter exits: this one is ignored then (see PythonEntry).
  template <typename... Args>
  std::function<void(Args...)> PythonCallback(pybind11::function function) {
    auto held = HeldFunction(std::move(function));
    return [held](const Args &...args) {
      const PythonEntry entry;
      if (!entry) {
        return;
      }
      const pybind11::gil_scoped_acquire gil;
      CallUnraisable("callback", [&]() { (*held)(args...); });
    };
  }

  // the exit fails them: their completions are dropped from then on
  class PendingOperations {
  public:
    struct Operation {
      std::atomic<bool> settled{false};
      std::function<void()> fail;
    };

    // with the GIL
    static std::shared_ptr<Operation> Start(std::function<void()> fail) {
      auto operation = std::make_shared<Operation>();
      operation->fail = std::move(fail);
      {
        const std::scoped_lock lock(Mutex());
        if (!PythonExiting()) {
          Operations().emplace(operation.get(), operation);
          return operation;
        }
      }
      operation->settled = true;
      operation->fail();
      return nullptr;
    }

    static bool Settle(Operation &operation) {
      if (operation.settled.exchange(true)) {
        return false;
      }
      const std::scoped_lock lock(Mutex());
      Operations().erase(&operation);
      return true;
    }

    // with the GIL, on the exiting thread
    static void FailAll() {
      std::unordered_map<Operation *, std::shared_ptr<Operation>> pending;
      {
        const std::scoped_lock lock(Mutex());
        pending.swap(Operations());
      }
      for (auto &[_, operation] : pending) {
        if (!operation->settled.exchange(true)) {
          operation->fail();
        }
      }
    }

  private:
    static std::mutex &Mutex() {
      static std::mutex mutex;
      return mutex;
    }

    static std::unordered_map<Operation *, std::shared_ptr<Operation>> &Operations() {
      static std::unordered_map<Operation *, std::shared_ptr<Operation>> operations;
      return operations;
    }
  };

  template <typename... Args>
  std::function<void(Args...)> SettlingCallback(std::shared_ptr<pybind11::function> held,
                                                std::shared_ptr<PendingOperations::Operation> operation) {
    return [held = std::move(held), operation = std::move(operation)](const Args &...args) {
      const PythonEntry entry;
      if (!entry || !PendingOperations::Settle(*operation)) {
        return;
      }
      const pybind11::gil_scoped_acquire gil;
      CallUnraisable("callback", [&]() { (*held)(args...); });
    };
  }

  // A method taking (onSuccess, onFailure, ...) callbacks, bound with PythonCallbacks and without the GIL
  template <typename C, typename... Result, typename... Rest>
  auto WithCallbacks(void (C::*method)(std::function<void(Result...)> &, std::function<void(RTCCallbackException)> &,
                                       Rest...)) {
    return [method](C &self, pybind11::function onSuccess, pybind11::function onFailure, Rest... rest) {
      auto onSuccessHeld = HeldFunction(std::move(onSuccess));
      auto onFailureHeld = HeldFunction(std::move(onFailure));
      auto operation = PendingOperations::Start([onFailureHeld]() {
        CallUnraisable("callback", [&]() {
          (*onFailureHeld)(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The interpreter is exiting"));
        });
      });
      if (!operation) {
        return;
      }
      auto success = SettlingCallback<Result...>(std::move(onSuccessHeld), operation);
      auto failure = SettlingCallback<RTCCallbackException>(std::move(onFailureHeld), operation);
      const gil_release release;
      (self.*method)(success, failure, std::forward<Rest>(rest)...);
    };
  }

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_PYTHON_CALLBACK_H_
