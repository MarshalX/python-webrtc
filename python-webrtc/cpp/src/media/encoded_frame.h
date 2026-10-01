//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_
#define PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_

#include <memory>
#include <mutex>

#include <api/frame_transformer_interface.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"

namespace python_webrtc {

  // An encoded frame of libwebrtc that Python reads (webrtc.RTCEncodedVideoFrame or RTCEncodedAudioFrame)
  class EncodedFrame {
  public:
    explicit EncodedFrame(std::unique_ptr<webrtc::TransformableFrameInterface> frame);

    static void Init(pybind11::module &m);

    [[nodiscard]] bool IsVideo() const { return _video; }

    // the payload, empty once taken
    pybind11::bytes GetData();

    // the metadata by its WebIDL names, plus "keyFrame" and "rid" of a video frame
    pybind11::dict GetMetadata();

    // the frame, null once taken
    std::unique_ptr<webrtc::TransformableFrameInterface> Take();

  private:
    AliveCount<EncodedFrame> _counted;
    const bool _video;

    std::mutex _mutex;
    std::unique_ptr<webrtc::TransformableFrameInterface> _frame;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_ENCODED_FRAME_H_
