//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_script_transform.h"

#include <cstring>
#include <utility>
#include <vector>

#include <pybind11/stl.h>

#include "../utils/buffer.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  std::shared_ptr<RTCRtpScriptTransform> RTCRtpScriptTransform::Create() {
    // the bridge may hold the last reference on a libwebrtc thread
    return {new RTCRtpScriptTransform(), DeleteOffLibwebrtcThread()};
  }

  RTCRtpScriptTransform::~RTCRtpScriptTransform() {
    const gil_release_if_held release;
    {
      const std::scoped_lock lock(_mutex);
      _queue.clear();
      _bridge = nullptr;
    }
    DropListeners();
  }

  void RTCRtpScriptTransform::Init(pybind11::module &m) {
    Listeners::BindClass<RTCRtpScriptTransform, RtpTransform>(m, "RTCRtpScriptTransform")
        .def(pybind11::init(nogil_factory(&RTCRtpScriptTransform::Create)))
        .def("read", &RTCRtpScriptTransform::Read)
        .def("write", &RTCRtpScriptTransform::Write, pybind11::arg("frame"), pybind11::arg("data"))
        .def("_ackWakeup", &RTCRtpScriptTransform::AckWakeup, nogil())
        .def_property_readonly("state",
                               nogil_fn([](RTCRtpScriptTransform &self) { return static_cast<int>(self.GetState()); }))
        .def_property_readonly("sourceId", nogil_fn(&RTCRtpScriptTransform::GetSourceId))
        .def_property_readonly("sourceKind", nogil_fn(&RTCRtpScriptTransform::GetSourceKind))
        .def(
            "generateKeyFrame",
            [](RTCRtpScriptTransform &self, const std::optional<std::string> &rid) {
              return static_cast<int>(self.GenerateKeyFrame(rid));
            },
            nogil(), pybind11::arg("rid"))
        .def("sendKeyFrameRequest", &RTCRtpScriptTransform::SendKeyFrameRequest, nogil());
  }

  void RTCRtpScriptTransform::Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    std::unique_ptr<webrtc::TransformableFrameInterface> dropped;
    const std::scoped_lock lock(_mutex);
    if (_state != State::kAssociated) {
      return;
    }
    if (_queue.size() >= kMaxQueuedFrames) {
      dropped = std::move(_queue.front());
      _queue.pop_front();
    }
    _queue.push_back(std::move(frame));
    WakeLocked();
  }

  void RTCRtpScriptTransform::Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) {
    const std::scoped_lock lock(_mutex);
    _bridge = std::move(bridge);
    _state = State::kAssociated;
  }

  void RTCRtpScriptTransform::Disassociate() {
    std::deque<std::unique_ptr<webrtc::TransformableFrameInterface>> dropped;
    const std::scoped_lock lock(_mutex);
    if (_state == State::kDisassociated) {
      return;
    }
    _state = State::kDisassociated;
    std::swap(dropped, _queue);
    // the end wakes Python even while a wakeup is pending
    _wakePending = false;
    WakeLocked();
  }

  void RTCRtpScriptTransform::WakeLocked() {
    if (!_wakePending) {
      _wakePending = true;
      Wakeup::Post(weak_from_this());
    }
  }

  void RTCRtpScriptTransform::OnWakeup() {
    // read before the event, whose delivery ends the streams then
    const bool ended = GetState() == State::kDisassociated;
    Emit("_ready");
    if (ended) {
      // never associated again: drops handlers that may reference the sender or receiver
      CloseListeners();
    }
  }

  void RTCRtpScriptTransform::AckWakeup() {
    const std::scoped_lock lock(_mutex);
    _wakePending = false;
  }

  std::shared_ptr<EncodedFrame> RTCRtpScriptTransform::Read() {
    std::unique_ptr<webrtc::TransformableFrameInterface> frame;
    uint64_t source = 0;
    {
      const gil_release release;
      const std::scoped_lock lock(_mutex);
      if (_queue.empty()) {
        return nullptr;
      }
      frame = std::move(_queue.front());
      _queue.pop_front();
      // frames are queued once associated, and the bridge is kept since
      source = _bridge->Id();
    }
    return std::make_shared<EncodedFrame>(std::move(frame), source);
  }

  bool RTCRtpScriptTransform::Write(EncodedFrame &frame, std::optional<pybind11::buffer> data) {
    std::optional<std::vector<uint8_t>> payload;
    if (data) {
      auto info = ContiguousBuffer(*data);
      const auto size = static_cast<size_t>(info.size * info.itemsize);
      payload.emplace(size);
      if (size > 0) {
        std::memcpy(payload->data(), info.ptr, size);
      }
    }
    const gil_release release;
    webrtc::scoped_refptr<FrameTransformerBridge> bridge;
    {
      const std::scoped_lock lock(_mutex);
      if (_state != State::kAssociated) {
        return false;
      }
      bridge = _bridge;
    }
    // a frame of another sender or receiver (another kind, direction) would be cast to what it isn't by libwebrtc
    if (frame.Source() != bridge->Id()) {
      return false;
    }
    auto transformable = frame.Take();
    if (!transformable) {
      return false;
    }
    if (payload) {
      transformable->SetData(*payload);
    }
    bridge->Output(std::move(transformable));
    return true;
  }

  webrtc::scoped_refptr<FrameTransformerBridge> RTCRtpScriptTransform::Bridge() {
    const std::scoped_lock lock(_mutex);
    return _bridge;
  }

  RTCRtpScriptTransform::State RTCRtpScriptTransform::GetState() {
    const std::scoped_lock lock(_mutex);
    return _state;
  }

  uint64_t RTCRtpScriptTransform::GetSourceId() {
    auto bridge = Bridge();
    return bridge ? bridge->Id() : 0;
  }

  std::optional<std::pair<bool, bool>> RTCRtpScriptTransform::GetSourceKind() {
    auto bridge = Bridge();
    if (!bridge) {
      return std::nullopt;
    }
    return std::make_pair(bridge->Source().sender, bridge->Source().video);
  }

  RTCRtpScriptTransform::KeyFrameResult RTCRtpScriptTransform::GenerateKeyFrame(const std::optional<std::string> &rid) {
    auto bridge = Bridge();
    if (!bridge || !bridge->Source().sender || !bridge->Source().video || !bridge->Source().generateKeyFrame) {
      return KeyFrameResult::kInvalidState;
    }
    std::vector<std::string> rids;
    if (rid) {
      rids.push_back(*rid);
    }
    return bridge->Source().generateKeyFrame(rids) == FrameSource::KeyFrameResult::kUnknownRid
               ? KeyFrameResult::kNotFound
               : KeyFrameResult::kRequested;
  }

  bool RTCRtpScriptTransform::SendKeyFrameRequest() {
    auto bridge = Bridge();
    if (!bridge || bridge->Source().sender || !bridge->Source().video || !bridge->Source().sendKeyFrameRequest) {
      return false;
    }
    bridge->Source().sendKeyFrameRequest();
    return true;
  }

} // namespace python_webrtc
