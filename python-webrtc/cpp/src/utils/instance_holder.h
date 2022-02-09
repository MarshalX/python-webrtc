//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <map>

namespace python_webrtc {

// T — Value. shared pointer to wrapped class
// U — Key. original webrtc class
// V — arguments to constructor of wrapped class
  template<typename T, typename U, typename ...V>
  class InstanceHolder {
  public:
    InstanceHolder() = delete;

    explicit InstanceHolder(T(*WrapConstructor)(V..., U)) : WrapConstructor(WrapConstructor) {}

    T GetOrCreate(V..., U);

    void Release(T value);

  private:
    T (*WrapConstructor)(V..., U);

    std::map<U, T> _uToTstore;
    std::map<T, U> _tToUstore;
  };

  template<typename T, typename U, typename... V>
  T InstanceHolder<T, U, V...>::GetOrCreate(V... args, U key) {
    if (_uToTstore.find(key) != _uToTstore.end()) {
      return _uToTstore.at(key);
    }

    auto instance = WrapConstructor(args..., key);
    _uToTstore[key] = instance;
    _tToUstore[instance] = key;

    return instance;
  }

  template<typename T, typename U, typename... V>
  void InstanceHolder<T, U, V...>::Release(T value) {
    auto key = _tToUstore.at(value);
    _tToUstore.erase(value);
    _uToTstore.erase(key);
  }

} // namespace python_webrtc
