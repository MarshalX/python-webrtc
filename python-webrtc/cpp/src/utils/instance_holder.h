//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_INSTANCE_HOLDER_H_
#define PYTHON_WEBRTC_UTILS_INSTANCE_HOLDER_H_

#include <functional>
#include <memory>
#include <mutex>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>

#include <api/scoped_refptr.h>

#include "gil.h"
#include "libwebrtc_thread.h"

namespace python_webrtc {

  class PeerConnectionFactory;

  // Runs a function on the signaling thread of a factory (defined with the factory)
  void RunOnSignalingThread(PeerConnectionFactory &factory, const std::function<void()> &function);

  // A wrapper of a libwebrtc object that takes a single observer: the holder tells which wrapper is registered, so a
  // dying one doesn't unregister a newer one (both done on the observer's thread)
  struct SingleObserverSlot {};

  // At most one wrapper T per libwebrtc object U, so Python always sees the same object for it. Entries are weak:
  // Python and parent wrappers own the wrappers.
  template <typename T, typename U>
  class InstanceHolder {
  public:
    std::shared_ptr<T> GetOrCreate(const std::shared_ptr<PeerConnectionFactory> &factory,
                                   webrtc::scoped_refptr<U> object) {
      if (!object) {
        return nullptr;
      }
      if (auto instance = Find(object.get())) {
        return instance;
      }
      if (!OnLibwebrtcThread()) {
        // wrappers are created on the signaling thread
        std::shared_ptr<T> instance;
        RunOnSignalingThread(*factory, [&]() { instance = GetOrCreate(factory, object); });
        return instance;
      }

      // unlocked: constructors may block on libwebrtc threads
      auto key = object.get();
      std::shared_ptr<T> instance(new T(factory, std::move(object)),
                                  [this, key, generation = Forks().load()](T *dying) {
                                    // left to the exit of the process (see ReleaseOffLibwebrtcThread): the lock may be
                                    // held by a hung thread
                                    if (!PythonAlive() || generation != Forks().load()) {
                                      return;
                                    }
                                    // the lock's holder may wait for a libwebrtc thread waiting for the GIL
                                    const gil_release_if_held release;
                                    StartDestroying(key);
                                    ReleaseOffLibwebrtcThread([this, key, dying]() { Destroy(key, dying); });
                                  });
      std::shared_ptr<T> existing;
      {
        const TrackedLock lock(_mutex);
        auto &entry = _store[key];
        existing = entry.lock();
        if (!existing) {
          entry = instance;
        }
      }
      return existing ? existing : instance;
    }

    // The live wrapper of a libwebrtc object, if there's one
    std::shared_ptr<T> Find(const U *object) {
      const TrackedLock lock(_mutex);
      auto it = _store.find(object);
      return it != _store.end() ? it->second.lock() : nullptr;
    }

    // wrappers alive or being destroyed, for tests (wrtc._alive)
    int Alive() {
      const TrackedLock lock(_mutex);
      int alive = static_cast<int>(_destroying.size());
      for (const auto &entry : _store) {
        alive += entry.second.expired() ? 0 : 1;
      }
      return alive;
    }

    // A wrapper registered as the observer of its object, on the observer's thread
    void SetObserver(const U *object, const T *wrapper) {
      const std::scoped_lock lock(_observersMutex);
      _observers[object] = wrapper;
    }

    // Whether a wrapper is still the observer of its object, which it no longer is then, on the observer's thread
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
    void StartDestroying(U *key) {
      const TrackedLock lock(_mutex);
      auto it = _store.find(key);
      if (it != _store.end() && it->second.expired()) {
        _store.erase(it);
      }
      _destroying.insert(key);
    }

    void Destroy(U *key, T *dying) {
      const gil_release_if_held release;

      // out of the lock: destructors block on libwebrtc threads
      delete dying;
      const TrackedLock lock(_mutex);
      _destroying.erase(_destroying.find(key));
    }

    std::mutex _mutex;
    std::unordered_map<const U *, std::weak_ptr<T>> _store;
    // objects whose wrapper is being destroyed
    std::unordered_multiset<U *> _destroying;
    std::mutex _observersMutex;
    std::unordered_map<const U *, const T *> _observers;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_INSTANCE_HOLDER_H_
