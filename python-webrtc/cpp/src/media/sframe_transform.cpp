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
    return NativeObject::Create(CipherSuiteOf(cipherSuite), encrypting);
  }

  SFrameTransform::~SFrameTransform() {
    {
      const std::scoped_lock lock(_mutex);
      _bridge = nullptr;
    }
  }

  void SFrameTransform::Init(pybind11::module &m) {
    SFrameContext::Init(m);
    DefineBinding(pybind11::class_<SFrameTransform, RtpTransform, Binding, std::shared_ptr<SFrameTransform>>(
                      m, "SFrameTransform"))
        .def_property_readonly("_id", &SFrameTransform::Id)
        .def(pybind11::init(&SFrameTransform::Create), pybind11::arg("cipherSuite"), pybind11::arg("encrypting"))
        .def_property_readonly("encrypting", &SFrameTransform::IsEncrypting)
        .def_property_readonly("state", nogil_fn(&SFrameTransform::GetState))
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
    // padding-only packets reach transforms as empty frames, with nothing to decrypt
    if (frame->GetData().empty()) {
      bridge->Output(std::move(frame));
      return;
    }
    auto result = _context.Decrypt(frame->GetData());
    if (result.error == SFrameError::kNone) {
      frame->SetData(result.data);
      bridge->Output(std::move(frame));
      return;
    }
    // the frame goes with the event; unbound, nobody gets it
    if (IsBound()) {
      Emit("error", static_cast<int>(result.error), result.keyId, EncodedFrame::Create(std::move(frame), bridge->Id()));
    }
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
  }

  int SFrameTransform::GetState() {
    const std::scoped_lock lock(_mutex);
    if (_disassociated) {
      return 2;
    }
    return _bridge ? 1 : 0;
  }

} // namespace python_webrtc
