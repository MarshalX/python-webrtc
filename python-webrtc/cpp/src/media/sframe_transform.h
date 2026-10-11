//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_
#define PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_

#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <tuple>

#include <api/frame_transformer_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "frame_transformer_bridge.h"
#include "sframe.h"

namespace python_webrtc {

  class SFrameTransform : public RtpTransform, public NativeObject<SFrameTransform>, public Emitter<SFrameTransform> {
  public:
    static constexpr const char *kName = "SFrameTransform";

    static std::shared_ptr<SFrameTransform> Create(int cipherSuite, bool encrypting);

    ~SFrameTransform() override;

    SFrameTransform(const SFrameTransform &) = delete;
    SFrameTransform &operator=(const SFrameTransform &) = delete;

    static void Init(pybind11::module &m);

    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) override;

    void Disassociate() override;

    [[nodiscard]] bool IsEncrypting() const { return _encrypting; }

    int GetState();

    SFrameContext &Context() { return _context; }

    pybind11::object Encrypt(const pybind11::buffer &data);

    // (plaintext or None, SFrameError, key id or None)
    std::tuple<pybind11::object, int, std::optional<uint64_t>> Decrypt(const pybind11::buffer &data);

  private:
    friend class NativeObject<SFrameTransform>;

    SFrameTransform(SFrameCipherSuite suite, bool encrypting);

    const bool _encrypting;
    SFrameContext _context;

    std::mutex _mutex;
    webrtc::scoped_refptr<FrameTransformerBridge> _bridge;
    bool _disassociated = false;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_SFRAME_TRANSFORM_H_
