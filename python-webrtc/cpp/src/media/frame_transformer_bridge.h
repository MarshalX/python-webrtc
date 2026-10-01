//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_FRAME_TRANSFORMER_BRIDGE_H_
#define PYTHON_WEBRTC_MEDIA_FRAME_TRANSFORMER_BRIDGE_H_

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <api/frame_transformer_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"

namespace python_webrtc {

  class FrameTransformerBridge;

  // A transform of the encoded frames of a sender or receiver (its transform attribute), done in Python or natively
  class RtpTransform {
  public:
    virtual ~RtpTransform() = default;

    RtpTransform() = default;

    RtpTransform(const RtpTransform &) = delete;
    RtpTransform &operator=(const RtpTransform &) = delete;

    // a transform has one sender or receiver for its whole life: false if it had one already
    bool TakeOwnership() { return !_owned.exchange(true); }

    // a frame of the sender or receiver, on a libwebrtc thread: given back with bridge.Output(), or dropped
    virtual void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) = 0;

    // frames come from the bridge from now on, and go back to it
    virtual void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) = 0;

    // no frames come anymore
    virtual void Disassociate() = 0;

    static void Init(pybind11::module &m);

  private:
    std::atomic<bool> _owned{false};
  };

  // What a bridge knows of its sender or receiver: functions hold it weakly, and do nothing once it's gone
  struct FrameSource {
    enum class KeyFrameResult : uint8_t { kRequested, kUnknownRid };

    bool sender = false;
    bool video = false;
    // key frames for the layers of the rids (every layer for none), of a video sender
    std::function<KeyFrameResult(const std::vector<std::string> &)> generateKeyFrame;
    // asks the remote sender for a key frame, for a video receiver
    std::function<void()> sendKeyFrameRequest;
  };

  // The frame transformer of a sender or receiver, installed once: frames go to its transform, or straight back
  class FrameTransformerBridge : public webrtc::FrameTransformerInterface {
  public:
    explicit FrameTransformerBridge(FrameSource source);

    ~FrameTransformerBridge() override;

    FrameTransformerBridge(const FrameTransformerBridge &) = delete;
    FrameTransformerBridge &operator=(const FrameTransformerBridge &) = delete;

    [[nodiscard]] const FrameSource &Source() const { return _source; }

    // the transform frames go to, null for none
    void SetTransform(std::shared_ptr<RtpTransform> transform);

    // gives a frame back to libwebrtc, on any thread
    void Output(std::unique_ptr<webrtc::TransformableFrameInterface> frame);

    // FrameTransformerInterface
    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void RegisterTransformedFrameCallback(webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback) override;

    void RegisterTransformedFrameSinkCallback(webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback,
                                              uint32_t ssrc) override;

    void UnregisterTransformedFrameCallback() override;

    void UnregisterTransformedFrameSinkCallback(uint32_t ssrc) override;

  private:
    AliveCount<FrameTransformerBridge> _counted;
    const FrameSource _source;

    std::mutex _mutex;
    std::shared_ptr<RtpTransform> _transform;
    webrtc::scoped_refptr<webrtc::TransformedFrameCallback> _callback;
    // video streams register one per SSRC (simulcast layers)
    std::map<uint32_t, webrtc::scoped_refptr<webrtc::TransformedFrameCallback>> _sinkCallbacks;
  };

  // The transform attribute of a sender or receiver, and the bridge installed for it
  class TransformSlot {
  public:
    std::shared_ptr<RtpTransform> Get();

    // InvalidStateError for a transform used elsewhere; installs the bridge on first use (calls libwebrtc, no GIL)
    void Set(const std::shared_ptr<RtpTransform> &transform, const std::function<FrameSource()> &source,
             const std::function<void(const webrtc::scoped_refptr<FrameTransformerBridge> &)> &install);

    // closed or gone: the transform (still the attribute) gets no frames anymore, the bridge passes them through
    void Release();

  private:
    // setters run one at a time, so transforms are associated in the order they're set
    std::mutex _setMutex;
    std::mutex _mutex;
    std::shared_ptr<RtpTransform> _transform;
    webrtc::scoped_refptr<FrameTransformerBridge> _bridge;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_FRAME_TRANSFORMER_BRIDGE_H_
