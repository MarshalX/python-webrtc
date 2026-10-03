//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "sframe_transform.h"

#include <limits>
#include <utility>
#include <vector>

#include <pybind11/stl.h>

#include "../utils/buffer.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"
#include "encoded_frame.h"

namespace python_webrtc {

  SFrameTransform::SFrameTransform(SFrameCipherSuite suite, bool encrypting)
      : _encrypting(encrypting), _context(suite) {}

  std::shared_ptr<SFrameTransform> SFrameTransform::Create(int cipherSuite, bool encrypting) {
    // the bridge may hold the last reference on a libwebrtc thread
    return {new SFrameTransform(CipherSuiteOf(cipherSuite), encrypting), DeleteOffLibwebrtcThread()};
  }

  SFrameTransform::~SFrameTransform() {
    const gil_release_if_held release;
    {
      const std::scoped_lock lock(_mutex);
      _errors.clear();
      _bridge = nullptr;
    }
    DropListeners();
  }

  void SFrameTransform::Init(pybind11::module &m) {
    SFrameContext::Init(m);
    Listeners::BindClass<SFrameTransform, RtpTransform>(m, "SFrameTransform")
        .def(pybind11::init(&SFrameTransform::Create), pybind11::arg("cipherSuite"), pybind11::arg("encrypting"))
        .def_property_readonly("encrypting", &SFrameTransform::IsEncrypting)
        .def(
            "setEncryptionKey",
            [](SFrameTransform &self, const pybind11::buffer &key, uint64_t keyId) {
              pybind11::buffer_info info;
              const auto span = BufferSpan(key, info);
              const gil_release release;
              return self.Context().SetEncryptionKey(span, keyId);
            },
            pybind11::arg("key"), pybind11::arg("keyId"))
        .def(
            "addDecryptionKey",
            [](SFrameTransform &self, const pybind11::buffer &key, uint64_t keyId) {
              pybind11::buffer_info info;
              const auto span = BufferSpan(key, info);
              const gil_release release;
              return self.Context().AddDecryptionKey(span, keyId);
            },
            pybind11::arg("key"), pybind11::arg("keyId"))
        .def(
            "removeDecryptionKey",
            [](SFrameTransform &self, uint64_t keyId) { self.Context().RemoveDecryptionKey(keyId); }, nogil(),
            pybind11::arg("keyId"))
        .def("encrypt", &SFrameTransform::Encrypt, pybind11::arg("data"))
        .def("decrypt", &SFrameTransform::Decrypt, pybind11::arg("data"));
  }

  pybind11::object SFrameTransform::Encrypt(const pybind11::buffer &data) {
    pybind11::buffer_info info;
    const auto span = BufferSpan(data, info);
    std::optional<Octets> out;
    {
      const gil_release release;
      out = _context.Encrypt(span);
    }
    if (!out) {
      return pybind11::none();
    }
    return Bytes(out->data(), out->size());
  }

  std::tuple<pybind11::object, int, std::optional<uint64_t>> SFrameTransform::Decrypt(const pybind11::buffer &data) {
    pybind11::buffer_info info;
    const auto span = BufferSpan(data, info);
    SFrameContext::Decrypted result;
    {
      const gil_release release;
      result = _context.Decrypt(span);
    }
    pybind11::object plaintext = pybind11::none();
    if (result.error == SFrameError::kNone) {
      plaintext = Bytes(result.data.data(), result.data.size());
    }
    return {plaintext, static_cast<int>(result.error), result.keyId};
  }

  void SFrameTransform::Transform(std::unique_ptr<webrtc::TransformableFrameInterface> frame) {
    webrtc::scoped_refptr<FrameTransformerBridge> bridge;
    {
      const std::scoped_lock lock(_mutex);
      bridge = _bridge;
    }
    // a frame that doesn't encrypt (no key) is dropped, never sent in clear
    if (!bridge) {
      return;
    }
    if (_encrypting) {
      auto out = _context.Encrypt(frame->GetData());
      if (!out) {
        return;
      }
      frame->SetData(*out);
      bridge->Output(std::move(frame));
      return;
    }
    auto result = _context.Decrypt(frame->GetData());
    if (result.error == SFrameError::kNone) {
      frame->SetData(result.data);
      bridge->Output(std::move(frame));
      return;
    }
    Error dropped;
    const std::scoped_lock lock(_mutex);
    if (_errors.size() >= kMaxQueuedErrors) {
      dropped = std::move(_errors.front());
      _errors.pop_front();
    }
    _errors.push_back(
        {.error = result.error, .keyId = result.keyId, .frame = std::move(frame), .source = bridge->Id()});
    WakeLocked();
  }

  void SFrameTransform::Associate(webrtc::scoped_refptr<FrameTransformerBridge> bridge) {
    const std::scoped_lock lock(_mutex);
    _bridge = std::move(bridge);
  }

  void SFrameTransform::Disassociate() {
    webrtc::scoped_refptr<FrameTransformerBridge> bridge;
    const std::scoped_lock lock(_mutex);
    bridge = std::move(_bridge);
    _disassociated = true;
    WakeLocked();
  }

  void SFrameTransform::WakeLocked() {
    if (!_wakePending) {
      _wakePending = true;
      Wakeup::Post(weak_from_this());
    }
  }

  void SFrameTransform::OnWakeup() {
    std::deque<Error> errors;
    bool ended = false;
    {
      const std::scoped_lock lock(_mutex);
      std::swap(errors, _errors);
      _wakePending = false;
      ended = _disassociated;
    }
    for (auto &error : errors) {
      Emit("error", static_cast<int>(error.error), error.keyId,
           std::make_shared<EncodedFrame>(std::move(error.frame), error.source));
    }
    if (ended) {
      // never associated again: drops handlers that may reference the sender or receiver
      CloseListeners();
    }
  }

} // namespace python_webrtc
