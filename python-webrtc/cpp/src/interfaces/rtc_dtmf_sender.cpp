//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtmf_sender.h"

#include <algorithm>

#include "../exceptions.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCDTMFSender::RTCDTMFSender(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::DtmfSenderInterface> dtmf)
      : _factory(std::move(factory)), _dtmf(std::move(dtmf)) {
    // Posted, not blocking: wrappers are created under locks that the signaling thread may wait for.
    // The destructor unregisters with a call to the signaling thread, which runs after this.
    _factory->_signalingThread->PostTask(_alive.Guard([this]() { _dtmf->RegisterObserver(this); }));
  }

  RTCDTMFSender::~RTCDTMFSender() {
    gil_release_if_held release;
    _factory->_signalingThread->BlockingCall([this]() { _dtmf->UnregisterObserver(); });
    DropListeners();
  }

  void RTCDTMFSender::Init(pybind11::module &m) {
    pybind11::class_<RTCDTMFSender, std::shared_ptr<RTCDTMFSender>> cls(
        m, "RTCDTMFSender", Listeners::TypeSetup<RTCDTMFSender>());
    Listeners::Bind(cls);
    cls.def("insertDTMF", &RTCDTMFSender::InsertDtmf, nogil())
        .def_property_readonly("toneBuffer", nogil_fn(&RTCDTMFSender::GetToneBuffer))
        .def("_surfaceBuffer", &RTCDTMFSender::SurfaceBuffer, nogil())
        .def_property_readonly("canInsertDTMF", nogil_fn(&RTCDTMFSender::GetCanInsertDtmf));
  }

  InstanceHolder<RTCDTMFSender, webrtc::DtmfSenderInterface> &RTCDTMFSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCDTMFSender, webrtc::DtmfSenderInterface>();
    return *holder;
  }

  void RTCDTMFSender::SetTransceiver(std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver) {
    std::lock_guard<std::mutex> lock(_mutex);
    _transceiver = std::move(transceiver);
  }

  void RTCDTMFSender::OnToneChange(const std::string &tone, const std::string &tone_buffer) {
    uint64_t insertion;
    {
      std::lock_guard<std::mutex> lock(_bufferMutex);
      insertion = _insertions;
    }
    Emit("tonechange", tone, tone_buffer, insertion);
  }

  void RTCDTMFSender::InsertDtmf(const std::string &tones, int duration, int interToneGap) {
    std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> lookup;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      lookup = _transceiver;
    }
    auto transceiver = lookup ? lookup() : nullptr;
    if (!transceiver || transceiver->stopping() || transceiver->stopped()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The transceiver of the sender is stopped");
    }
    auto direction = transceiver->current_direction();
    if (direction && (*direction == webrtc::RtpTransceiverDirection::kRecvOnly ||
                      *direction == webrtc::RtpTransceiverDirection::kInactive)) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The transceiver of the sender doesn't send");
    }
    if (tones.empty() && _dtmf->tones().empty()) {
      // nothing to play, nor to cancel
      return;
    }
    {
      // tone changes of the tones inserted before don't change the buffer anymore
      std::lock_guard<std::mutex> lock(_bufferMutex);
      ++_insertions;
    }
    // libwebrtc takes longer tones and gaps than the specification
    if (!_dtmf->InsertDtmf(tones, std::max(duration, 70), std::max(interToneGap, 50)) && !tones.empty()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The DTMF sender can't send tones yet");
    }
    std::lock_guard<std::mutex> lock(_bufferMutex);
    _surfacedBuffer = tones;
  }

  std::string RTCDTMFSender::GetToneBuffer() {
    {
      std::lock_guard<std::mutex> lock(_bufferMutex);
      if (HasListeners() && _surfacedBuffer) {
        return *_surfacedBuffer;
      }
    }
    return _dtmf->tones();
  }

  void RTCDTMFSender::SurfaceBuffer(const std::string &buffer, uint64_t insertion) {
    std::lock_guard<std::mutex> lock(_bufferMutex);
    // a tone played before the last insertDTMF() doesn't change what it set
    if (insertion == _insertions) {
      _surfacedBuffer = buffer;
    }
  }

  bool RTCDTMFSender::GetCanInsertDtmf() {
    return _dtmf->CanInsertDtmf();
  }

} // namespace python_webrtc
