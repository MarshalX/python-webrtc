//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_
#define PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_

#include <cstdint>
#include <memory>
#include <mutex>

#include <api/frame_transformer_interface.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"

namespace python_webrtc {

  class EncodedFrame {
  public:
    EncodedFrame(std::unique_ptr<webrtc::TransformableFrameInterface> frame, uint64_t source);

    static void Init(pybind11::module &m);

    [[nodiscard]] bool IsVideo() const { return _video; }

    [[nodiscard]] uint64_t Source() const { return _source; }

    pybind11::bytes GetData();

    pybind11::dict GetMetadata();

    std::unique_ptr<webrtc::TransformableFrameInterface> Take();

  private:
    AliveCount<EncodedFrame> _counted;
    const bool _video;
    const uint64_t _source;

    // never held while taking the GIL: a thread with it may wait for the lock (Take() comes without it)
    std::mutex _mutex;
    std::unique_ptr<webrtc::TransformableFrameInterface> _frame;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_
