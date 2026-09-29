//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <cstddef>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // A Python buffer used as one block: a strided view (like view[::-1]) would be accessed out of its bounds
  inline pybind11::buffer_info ContiguousBuffer(const pybind11::buffer &buffer, bool writable = false) {
    auto info = buffer.request(writable);
    if (!PyBuffer_IsContiguous(info.view(), 'C')) {
      throw pybind11::type_error("The buffer must be contiguous");
    }
    return info;
  }

  // Whether rows of rowBytes, stride apart and starting at offset, fit in size bytes, without overflowing
  inline bool RowsFit(size_t offset, size_t stride, size_t rows, size_t rowBytes, size_t size) {
    if (rows == 0 || rowBytes == 0) {
      return true;
    }
    if (offset > size || rowBytes > size - offset) {
      return false;
    }
    return rows == 1 || stride <= (size - offset - rowBytes) / (rows - 1);
  }

} // namespace python_webrtc
