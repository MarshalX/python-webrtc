//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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

#include "../utils/alive_count.h"
#include "../utils/listeners.h"
#include "encoded_frame.h"
#include "frame_transformer_bridge.h"
#include "wakeup.h"

namespace python_webrtc {

  // Queues the frames of a sender or receiver for Python (webrtc.RTCRtpScriptTransform), woken with "_ready"
  class RTCRtpScriptTransform : public RtpTransform,
                                public Listeners,
                                public Wakeable,
                                public std::enable_shared_from_this<RTCRtpScriptTransform> {
  public:
    // frames queued for a transformer that doesn't read them, before the oldest is dropped
    static constexpr size_t kMaxQueuedFrames = 120;

    // whether frames come: not yet, from a sender or receiver, or not anymore
    enum class State : uint8_t { kNew, kAssociated, kDisassociated };

    // the result of generateKeyFrame: requested, InvalidStateError (not a video sender) or NotFoundError
    enum class KeyFrameResult : uint8_t { kRequested, kInvalidState, kNotFound };

    static std::shared_ptr<RTCRtpScriptTransform> Create();

    ~RTCRtpScriptTransform() override;

    RTCRtpScriptTransform(const RTCRtpScriptTransform &) = delete;
    RTCRtpScriptTransform &operator=(const RTCRtpScriptTransform &) = delete;

    static void Init(pybind11::module &m);

    // RtpTransform
    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) override;

    void Disassociate() override;

    // Wakeable
    void OnWakeup() override;

    // the oldest frame queued, or None
    std::shared_ptr<EncodedFrame> Read();

    // gives a frame back to its sender or receiver with new data, if associated; false if dropped
    bool Write(EncodedFrame &frame, std::optional<pybind11::buffer> data);

    // Python got the wakeup: the next frame wakes it again
    void AckWakeup();

    State GetState();

    // identifies the sender or receiver (its bridge), 0 before one
    uint64_t GetSourceId();

    // (is a sender, is video) of the sender or receiver, None before one
    std::optional<std::pair<bool, bool>> GetSourceKind();

    KeyFrameResult GenerateKeyFrame(const std::optional<std::string> &rid);

    // false if not a video receiver
    bool SendKeyFrameRequest();

  private:
    RTCRtpScriptTransform() = default;

    webrtc::scoped_refptr<FrameTransformerBridge> Bridge();

    // wakes Python, unless a wakeup is pending
    void WakeLocked();

    AliveCount<RTCRtpScriptTransform> _counted;

    std::mutex _mutex;
    State _state = State::kNew;
    // kept once disassociated: key frames are still requested from it
    webrtc::scoped_refptr<FrameTransformerBridge> _bridge;
    std::deque<std::unique_ptr<webrtc::TransformableFrameInterface>> _queue;
    bool _wakePending = false;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_RTC_RTP_SCRIPT_TRANSFORM_H_
