//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_REGISTRY_H_
#define PYTHON_WEBRTC_UTILS_REGISTRY_H_

#include <iterator>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>

#include <api/scoped_refptr.h>

#include "../interfaces/peer_connection_factory.h"
#include "libwebrtc_thread.h"
#include "native_object.h"

namespace python_webrtc {

  // entries are weak: Python and parent wrappers own the wrappers
  template <typename T, typename U>
  class Registry {
  public:
    std::shared_ptr<T> GetOrCreate(const std::shared_ptr<PeerConnectionFactory> &factory,
                                   webrtc::scoped_refptr<U> object) {
      if (!object) {
        return nullptr;
      }
      if (auto instance = Find(object.get())) {
        return instance;
      }
      if (!factory->IsCurrent()) {
        std::shared_ptr<T> instance;
        BlockingCallOn(factory->signalingThread(), [&]() { instance = GetOrCreate(factory, object); });
        return instance;
      }

      // unlocked: constructors may block on libwebrtc threads
      const U *key = object.get();
      auto instance = NativeObject<T>::Create(factory, std::move(object));
      const TrackedLock lock(_mutex);
      Sweep();
      auto &entry = _store[key];
      if (auto existing = entry.lock()) {
        return existing;
      }
      entry = instance;
      return instance;
    }

    std::shared_ptr<T> Find(const U *object) {
      const TrackedLock lock(_mutex);
      auto it = _store.find(object);
      return it != _store.end() ? it->second.lock() : nullptr;
    }

    // libwebrtc takes one observer per object: a dying wrapper mustn't unregister a newer one
    void SetObserver(const U *object, const T *wrapper) {
      const std::scoped_lock lock(_observersMutex);
      _observers[object] = wrapper;
    }

    bool TakeObserver(const U *object, const T *wrapper) {
      const std::scoped_lock lock(_observersMutex);
      auto it = _observers.find(object);
      if (it == _observers.end() || it->second != wrapper) {
        return false;
      }
      _observers.erase(it);
      return true;
    }

  private:
    void Sweep() {
      for (auto it = _store.begin(); it != _store.end();) {
        it = it->second.expired() ? _store.erase(it) : std::next(it);
      }
    }

    std::mutex _mutex;
    std::unordered_map<const U *, std::weak_ptr<T>> _store;
    std::mutex _observersMutex;
    std::unordered_map<const U *, const T *> _observers;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_REGISTRY_H_
