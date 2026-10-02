//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_
#define PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_

#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <optional>
#include <tuple>

#include <api/frame_transformer_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"
#include "../utils/listeners.h"
#include "frame_transformer_bridge.h"
#include "sframe.h"
#include "wakeup.h"

namespace python_webrtc {

  class SFrameTransform : public RtpTransform,
                          public Listeners,
                          public Wakeable,
                          public std::enable_shared_from_this<SFrameTransform> {
  public:
    static constexpr size_t kMaxQueuedErrors = 120;

    static std::shared_ptr<SFrameTransform> Create(int cipherSuite, bool encrypting);

    ~SFrameTransform() override;

    SFrameTransform(const SFrameTransform &) = delete;
    SFrameTransform &operator=(const SFrameTransform &) = delete;

    static void Init(pybind11::module &m);

    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) override;

    void Disassociate() override;

    void OnWakeup() override;

    [[nodiscard]] bool IsEncrypting() const { return _encrypting; }

    SFrameContext &Context() { return _context; }

    pybind11::object Encrypt(const pybind11::buffer &data);

    // (plaintext or None, SFrameError, key id or None)
    std::tuple<pybind11::object, int, std::optional<uint64_t>> Decrypt(const pybind11::buffer &data);

  private:
    SFrameTransform(SFrameCipherSuite suite, bool encrypting);

    void WakeLocked();

    struct Error {
      SFrameError error = SFrameError::kNone;
      std::optional<uint64_t> keyId;
      std::unique_ptr<webrtc::TransformableFrameInterface> frame;
      uint64_t source = 0;
    };

    AliveCount<SFrameTransform> _counted;
    const bool _encrypting;
    SFrameContext _context;

    std::mutex _mutex;
    webrtc::scoped_refptr<FrameTransformerBridge> _bridge;
    std::deque<Error> _errors;
    bool _wakePending = false;
    bool _disassociated = false;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_
