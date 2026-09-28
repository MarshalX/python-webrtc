//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>
#include <unordered_map>

#include <api/scoped_refptr.h>

#include "gil.h"

namespace python_webrtc {

  class PeerConnectionFactory;

  // Keeps at most one wrapper per libwebrtc object, so Python always sees the same object for it.
  // Entries are weak: the cache never keeps a wrapper, nor the libwebrtc object behind it, alive.
  // Ownership lives in shared_ptrs held by Python and by parent wrappers.
  //
  // T — wrapper class, constructible from (std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<U>)
  // U — wrapped libwebrtc interface
  template<typename T, typename U>
  class InstanceHolder {
  public:
    std::shared_ptr<T> GetOrCreate(const std::shared_ptr<PeerConnectionFactory> &factory, webrtc::scoped_refptr<U> object) {
      if (!object) {
        return nullptr;
      }

      // wrappers may create nested wrappers (sctp -> dtls -> ice) while holding the lock
      std::lock_guard<std::recursive_mutex> lock(_mutex);
      auto key = object.get();
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

    // Whether another wrapper of the same libwebrtc object is alive. Only meaningful in a destructor of the wrapper,
    // where it tells that the object was re-wrapped meanwhile and the new wrapper has taken over its observer slot.
    bool HasLive(const U *object) {
      std::lock_guard<std::recursive_mutex> lock(_mutex);
      auto it = _store.find(const_cast<U *>(object));
      return it != _store.end() && !it->second.expired();
    }

  private:
    void Destroy(U *key, T *dying) {
      gil_release_if_held release;

      // destroy under the lock, so a replacement can't register its observers while this one unregisters
      std::lock_guard<std::recursive_mutex> lock(_mutex);
      auto it = _store.find(key);
      if (it != _store.end() && it->second.expired()) {
        _store.erase(it);
      }
      delete dying;
    }

    std::recursive_mutex _mutex;
    std::unordered_map<U *, std::weak_ptr<T>> _store;
  };

} // namespace python_webrtc
