//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_BUFFER_H_
#define PYTHON_WEBRTC_UTILS_BUFFER_H_

#include <cstddef>
#include <cstdint>
#include <span>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // A Python buffer used as one block: a strided view (like view[::-1]) would be accessed out of its bounds
  inline pybind11::buffer_info ContiguousBuffer(const pybind11::buffer &buffer, bool writable = false) {
    auto info = buffer.request(writable);
    if (PyBuffer_IsContiguous(info.view(), 'C') == 0) {
      throw pybind11::type_error("The buffer must be contiguous");
    }
    return info;
  }

  // the octets of a contiguous buffer, valid while info is
  inline std::span<const uint8_t> BufferSpan(const pybind11::buffer &buffer, pybind11::buffer_info &info) {
    info = ContiguousBuffer(buffer);
    return {static_cast<const uint8_t *>(info.ptr), static_cast<size_t>(info.size * info.itemsize)};
  }

  // bytes of a buffer of octets
  inline pybind11::bytes Bytes(const uint8_t *data, size_t size) {
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast): Python bytes are chars, octets alias them
    return {reinterpret_cast<const char *>(data), size};
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

#endif // PYTHON_WEBRTC_UTILS_BUFFER_H_
