//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <pybind11/cast.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "absl/types/optional.h"

namespace pybind11::detail {
  template<typename T> struct type_caster<absl::optional < T>>: public optional_caster <absl::optional<T>> {};
  template<> struct type_caster<absl::nullopt_t> : public void_caster<absl::nullopt_t> {};
} // namespace pybind11::detail
