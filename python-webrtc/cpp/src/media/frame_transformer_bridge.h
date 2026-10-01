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

  class RtpTransform {
  public:
    virtual ~RtpTransform() = default;

    RtpTransform() = default;

    RtpTransform(const RtpTransform &) = delete;
    RtpTransform &operator=(const RtpTransform &) = delete;

    bool TakeOwnership() { return !_owned.exchange(true); }

    // on a libwebrtc thread: the frame goes back with bridge.Output(), or is dropped
    virtual void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) = 0;

    virtual void Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) = 0;

    virtual void Disassociate() = 0;

    static void Init(pybind11::module &m);

  private:
    std::atomic<bool> _owned{false};
  };

  // the functions hold the sender or receiver weakly, and do nothing once it's gone
  struct FrameSource {
    enum class KeyFrameResult : uint8_t { kRequested, kUnknownRid };

    bool sender = false;
    bool video = false;
    std::function<KeyFrameResult(const std::vector<std::string> &)> generateKeyFrame;
    std::function<void()> sendKeyFrameRequest;
  };

  class FrameTransformerBridge : public webrtc::FrameTransformerInterface {
  public:
    explicit FrameTransformerBridge(FrameSource source);

    ~FrameTransformerBridge() override;

    FrameTransformerBridge(const FrameTransformerBridge &) = delete;
    FrameTransformerBridge &operator=(const FrameTransformerBridge &) = delete;

    [[nodiscard]] const FrameSource &Source() const { return _source; }

    // identifies the bridge for the frames it gives, never reused (unlike its address)
    [[nodiscard]] uint64_t Id() const { return _id; }

    void SetTransform(std::shared_ptr<RtpTransform> transform);

    void Output(std::unique_ptr<webrtc::TransformableFrameInterface> frame);

    void Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) override;

    void RegisterTransformedFrameCallback(webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback) override;

    void RegisterTransformedFrameSinkCallback(webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback,
                                              uint32_t ssrc) override;

    void UnregisterTransformedFrameCallback() override;

    void UnregisterTransformedFrameSinkCallback(uint32_t ssrc) override;

  private:
    AliveCount<FrameTransformerBridge> _counted;
    const FrameSource _source;
    const uint64_t _id;

    std::mutex _mutex;
    std::shared_ptr<RtpTransform> _transform;
    webrtc::scoped_refptr<webrtc::TransformedFrameCallback> _callback;
    // video streams register one per SSRC (simulcast layers)
    std::map<uint32_t, webrtc::scoped_refptr<webrtc::TransformedFrameCallback>> _sinkCallbacks;
  };

  class TransformSlot {
  public:
    std::shared_ptr<RtpTransform> Get();

    // calls libwebrtc: without the GIL
    void Set(const std::shared_ptr<RtpTransform> &transform, const std::function<FrameSource()> &source,
             const std::function<void(const webrtc::scoped_refptr<FrameTransformerBridge> &)> &install);

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
