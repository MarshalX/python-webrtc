//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_RTC_RTP_SCRIPT_TRANSFORM_H_
#define PYTHON_WEBRTC_MEDIA_RTC_RTP_SCRIPT_TRANSFORM_H_

#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <api/frame_transformer_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "encoded_frame.h"
#include "frame_transformer_bridge.h"

namespace python_webrtc {

  class RTCRtpScriptTransform : public RtpTransform,
                                public NativeObject<RTCRtpScriptTransform>,
                                public Emitter<RTCRtpScriptTransform> {
  public:
    static constexpr const char *kName = "RTCRtpScriptTransform";
    static constexpr size_t kMaxQueuedFrames = 120;

    enum class State : uint8_t { kNew, kAssociated, kDisassociated };

    enum class KeyFrameResult : uint8_t { kRequested, kInvalidState, kNotFound };

    ~RTCRtpScriptTransform() override;

    RTCRtpScriptTransform(const RTCRtpScriptTransform &) = delete;
    RTCRtpScriptTransform &operator=(const RTCRtpScriptTransform &) = delete;

    static void Init(pybind11::module &m);

    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) override;

    void Disassociate() override;

    std::shared_ptr<EncodedFrame> Read();

    bool Write(EncodedFrame &frame, std::optional<pybind11::buffer> data);

    void AckWakeup();

    State GetState();

    uint64_t GetSourceId();

    // (sender, video)
    std::optional<std::pair<bool, bool>> GetSourceKind();

    KeyFrameResult GenerateKeyFrame(const std::optional<std::string> &rid);

    bool SendKeyFrameRequest();

  private:
    friend class NativeObject<RTCRtpScriptTransform>;

    RTCRtpScriptTransform() = default;

    webrtc::scoped_refptr<FrameTransformerBridge> Bridge();

    bool ArmWakeLocked();

    std::mutex _mutex;
    State _state = State::kNew;
    // kept once disassociated: key frames are still requested from it
    webrtc::scoped_refptr<FrameTransformerBridge> _bridge;
    std::deque<std::unique_ptr<webrtc::TransformableFrameInterface>> _queue;
    bool _wakePending = false;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_RTC_RTP_SCRIPT_TRANSFORM_H_
