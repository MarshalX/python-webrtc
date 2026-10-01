//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "frame_transformer_bridge.h"

#include <utility>

#include <api/make_ref_counted.h>

#include "../exceptions.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  void RtpTransform::Init(pybind11::module &m) {
    // the base of the transforms the transform attributes take
    pybind11::class_<RtpTransform, std::shared_ptr<RtpTransform>>(m, "_RtpTransform");
  }

  FrameTransformerBridge::FrameTransformerBridge(FrameSource source) : _source(std::move(source)) {}

  FrameTransformerBridge::~FrameTransformerBridge() {
    // libwebrtc may release the bridge on its threads: the transform is then deleted elsewhere
    const LibwebrtcThreadScope scope;
    _transform.reset();
  }

  void FrameTransformerBridge::SetTransform(std::shared_ptr<RtpTransform> transform) {
    std::shared_ptr<RtpTransform> previous;
    const std::scoped_lock lock(_mutex);
    // released out of the lock
    previous = std::exchange(_transform, std::move(transform));
  }

  void FrameTransformerBridge::Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    // a transform replaced meanwhile is deleted elsewhere (see DeleteOffLibwebrtcThread)
    const LibwebrtcThreadScope scope;
    std::shared_ptr<RtpTransform> transform;
    {
      const std::scoped_lock lock(_mutex);
      transform = _transform;
    }
    if (transform) {
      transform->Transform(std::move(frame));
    } else {
      Output(std::move(frame));
    }
  }

  void FrameTransformerBridge::Output(std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback;
    {
      const std::scoped_lock lock(_mutex);
      auto it = _sinkCallbacks.find(frame->GetSsrc());
      callback = it != _sinkCallbacks.end() ? it->second : _callback;
    }
    // called out of the lock: it posts to the stream's queue, whose thread may be registering a callback
    if (callback) {
      callback->OnTransformedFrame(std::move(frame));
    }
  }

  void FrameTransformerBridge::RegisterTransformedFrameCallback(
      webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback) {
    const std::scoped_lock lock(_mutex);
    _callback = std::move(callback);
  }

  void FrameTransformerBridge::RegisterTransformedFrameSinkCallback(
      webrtc::scoped_refptr<webrtc::TransformedFrameCallback> callback, uint32_t ssrc) {
    const std::scoped_lock lock(_mutex);
    _sinkCallbacks[ssrc] = std::move(callback);
  }

  void FrameTransformerBridge::UnregisterTransformedFrameCallback() {
    webrtc::scoped_refptr<webrtc::TransformedFrameCallback> previous;
    const std::scoped_lock lock(_mutex);
    previous = std::move(_callback);
  }

  void FrameTransformerBridge::UnregisterTransformedFrameSinkCallback(uint32_t ssrc) {
    webrtc::scoped_refptr<webrtc::TransformedFrameCallback> previous;
    const std::scoped_lock lock(_mutex);
    auto it = _sinkCallbacks.find(ssrc);
    if (it != _sinkCallbacks.end()) {
      previous = std::move(it->second);
      _sinkCallbacks.erase(it);
    }
  }

  std::shared_ptr<RtpTransform> TransformSlot::Get() {
    const std::scoped_lock lock(_mutex);
    return _transform;
  }

  void TransformSlot::Set(const std::shared_ptr<RtpTransform> &transform, const std::function<FrameSource()> &source,
                          const std::function<void(const webrtc::scoped_refptr<FrameTransformerBridge> &)> &install) {
    const std::scoped_lock setLock(_setMutex);
    if (transform && transform == Get()) {
      // set again on its sender or receiver, as browsers allow
      return;
    }
    if (transform && !transform->TakeOwnership()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE,
                         "The transform is already used by an RTCRtpSender or RTCRtpReceiver");
    }
    webrtc::scoped_refptr<FrameTransformerBridge> bridge;
    std::shared_ptr<RtpTransform> previous;
    bool installing = false;
    {
      const std::scoped_lock lock(_mutex);
      if (!_bridge && transform) {
        _bridge = webrtc::make_ref_counted<FrameTransformerBridge>(source());
        installing = true;
      }
      bridge = _bridge;
      previous = std::exchange(_transform, transform);
    }
    if (transform) {
      transform->Associate(bridge);
    }
    if (bridge) {
      bridge->SetTransform(transform);
    }
    if (previous) {
      previous->Disassociate();
    }
    // after the transform is set: frames may come right away
    if (installing) {
      install(bridge);
    }
  }

  void TransformSlot::Release() {
    const std::scoped_lock setLock(_setMutex);
    std::shared_ptr<RtpTransform> transform;
    webrtc::scoped_refptr<FrameTransformerBridge> bridge;
    {
      const std::scoped_lock lock(_mutex);
      transform = _transform;
      bridge = _bridge;
    }
    if (bridge) {
      bridge->SetTransform(nullptr);
    }
    if (transform) {
      transform->Disassociate();
    }
  }

} // namespace python_webrtc
