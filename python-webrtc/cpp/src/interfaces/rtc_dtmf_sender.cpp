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
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  RTCDTMFSender::RTCDTMFSender(std::shared_ptr<PeerConnectionFactory> factory,
                               webrtc::scoped_refptr<webrtc::DtmfSenderInterface> dtmf)
      : _factory(std::move(factory)), _dtmf(std::move(dtmf)) {
    // see AliveGuard
    _factory->signalingThread()->PostTask(_alive.Guard([this]() {
      _dtmf->RegisterObserver(this);
      holder().SetObserver(_dtmf.get(), this);
    }));
  }

  RTCDTMFSender::~RTCDTMFSender() {
    const BlockingDestructor release("RTCDTMFSender");

    // callbacks run on the signaling thread, so after this none of them can be running or start again
    _factory->signalingThread()->BlockingCall([this]() {
      // a newer wrapper of the sender may have taken its single observer slot
      if (holder().TakeObserver(_dtmf.get(), this)) {
        _dtmf->UnregisterObserver();
      }
    });
    DropListeners();
  }

  void RTCDTMFSender::Init(pybind11::module &m) {
    Listeners::BindClass<RTCDTMFSender>(m, "RTCDTMFSender")
        .def_property_readonly("toneBuffer", nogil_fn(&RTCDTMFSender::GetToneBuffer))
        .def_property_readonly("canInsertDTMF", nogil_fn(&RTCDTMFSender::GetCanInsertDtmf))
        .def("insertDTMF", &RTCDTMFSender::InsertDtmf, nogil(), pybind11::arg("tones"), pybind11::arg("duration"),
             pybind11::arg("interToneGap"))
        .def("_surfaceBuffer", &RTCDTMFSender::SurfaceBuffer, nogil(), pybind11::arg("buffer"),
             pybind11::arg("insertion"));
  }

  InstanceHolder<RTCDTMFSender, webrtc::DtmfSenderInterface> &RTCDTMFSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto *holder = new InstanceHolder<RTCDTMFSender, webrtc::DtmfSenderInterface>();
    return *holder;
  }

  void
  RTCDTMFSender::SetTransceiver(std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver) {
    _transceiver.Set(std::move(transceiver));
  }

  void RTCDTMFSender::OnToneChange(const std::string &tone, const std::string &toneBuffer) {
    uint64_t insertion = 0;
    {
      const std::scoped_lock lock(_bufferMutex);
      insertion = _insertions;
    }
    Emit("tonechange", tone, toneBuffer, insertion);
  }

  void RTCDTMFSender::InsertDtmf(const std::string &tones, int duration, int interToneGap) {
    auto lookup = _transceiver.Get();
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
      const std::scoped_lock lock(_bufferMutex);
      ++_insertions;
    }
    // libwebrtc takes longer tones and gaps than the specification
    constexpr int minDuration = 70;
    constexpr int minInterToneGap = 50;
    if (!_dtmf->InsertDtmf(tones, std::max(duration, minDuration), std::max(interToneGap, minInterToneGap)) &&
        !tones.empty()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The DTMF sender can't send tones yet");
    }
    const std::scoped_lock lock(_bufferMutex);
    _surfacedBuffer = tones;
  }

  std::string RTCDTMFSender::GetToneBuffer() {
    {
      const std::scoped_lock lock(_bufferMutex);
      if (HasListeners() && _surfacedBuffer) {
        return *_surfacedBuffer;
      }
    }
    return _dtmf->tones();
  }

  void RTCDTMFSender::SurfaceBuffer(const std::string &buffer, uint64_t insertion) {
    const std::scoped_lock lock(_bufferMutex);
    // a tone played before the last insertDTMF() doesn't change what it set
    if (insertion == _insertions) {
      _surfacedBuffer = buffer;
    }
  }

  bool RTCDTMFSender::GetCanInsertDtmf() {
    return _dtmf->CanInsertDtmf();
  }

} // namespace python_webrtc
