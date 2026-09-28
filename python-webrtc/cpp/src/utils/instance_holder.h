//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <condition_variable>
#include <memory>
#include <mutex>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>

#include <api/scoped_refptr.h>

#include "gil.h"

namespace python_webrtc {

  class PeerConnectionFactory;

  // A wrapper of a libwebrtc object that takes a single observer: a new wrapper of the object must not register
  // before the dying one has unregistered. Wrappers of objects that take any number of observers don't wait.
  struct SingleObserverSlot {};

  // At most one wrapper T per libwebrtc object U, so Python always sees the same object for it. Entries are weak:
  // Python and parent wrappers own the wrappers.
  template<typename T, typename U>
  class InstanceHolder {
  public:
    std::shared_ptr<T> GetOrCreate(const std::shared_ptr<PeerConnectionFactory> &factory, webrtc::scoped_refptr<U> object) {
      if (!object) {
        return nullptr;
      }

      // wrappers may create nested wrappers (sctp -> dtls -> ice) while holding the lock
      std::unique_lock<std::recursive_mutex> lock(_mutex);
      auto key = object.get();
      // a wrapper of the object being destroyed first unregisters from it, the new one registers after
      if constexpr (std::is_base_of_v<SingleObserverSlot, T>) {
        _destroyed.wait(lock, [&]() { return _destroying.count(key) == 0; });
      }
      auto it = _store.find(key);
      if (it != _store.end()) {
        if (auto instance = it->second.lock()) {
          return instance;
        }
      }

      std::shared_ptr<T> instance(new T(factory, std::move(object)), [this, key](T *dying) { Destroy(key, dying); });
      _store[key] = instance;
      return instance;
    }

    // The live wrapper of a libwebrtc object, if there's one
    std::shared_ptr<T> Find(const U *object) {
      std::lock_guard<std::recursive_mutex> lock(_mutex);
      auto it = _store.find(const_cast<U *>(object));
      return it != _store.end() ? it->second.lock() : nullptr;
    }

    // Whether another wrapper of the same libwebrtc object is alive. Only meaningful in a destructor of the wrapper,
    // where it tells that the object was re-wrapped meanwhile and the new wrapper has taken over its observer slot.
    bool HasLive(const U *object) {
      // called from the destructor of the dying wrapper, which Destroy runs without holding the lock
      std::lock_guard<std::recursive_mutex> lock(_mutex);
      auto it = _store.find(const_cast<U *>(object));
      return it != _store.end() && !it->second.expired();
    }

  private:
    void Destroy(U *key, T *dying) {
      gil_release_if_held release;

      {
        std::lock_guard<std::recursive_mutex> lock(_mutex);
        auto it = _store.find(key);
        if (it != _store.end() && it->second.expired()) {
          _store.erase(it);
        }
        _destroying.insert(key);
      }
      // Out of the lock: destructors block on libwebrtc threads (to unregister observers), which may be waiting
      // for this lock themselves (a callback wrapping an object). A replacement waits for this to finish.
      delete dying;
      {
        std::lock_guard<std::recursive_mutex> lock(_mutex);
        _destroying.erase(_destroying.find(key));
      }
      _destroyed.notify_all();
    }

    std::recursive_mutex _mutex;
    std::condition_variable_any _destroyed;
    std::unordered_map<U *, std::weak_ptr<T>> _store;
    // objects whose wrapper is being destroyed
    std::unordered_multiset<U *> _destroying;
  };

} // namespace python_webrtc
