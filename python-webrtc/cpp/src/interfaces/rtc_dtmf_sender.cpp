//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtmf_sender.h"

#include "../exceptions.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  RTCDTMFSender::RTCDTMFSender(std::shared_ptr<PeerConnectionFactory> factory,
                               webrtc::scoped_refptr<webrtc::DtmfSenderInterface> dtmf)
      : _factory(std::move(factory)), _dtmf(std::move(dtmf)) {
    _factory->signalingThread()->PostTask(Guard([this]() {
      _dtmf->RegisterObserver(this);
      registry().SetObserver(_dtmf.get(), this);
    }));
  }

  RTCDTMFSender::~RTCDTMFSender() {
    // callbacks run on the signaling thread, so after this none of them can be running or start again
    BlockingCallOn(_factory->signalingThread(), [this]() {
      // a newer wrapper of the sender may have taken its single observer slot
      if (registry().TakeObserver(_dtmf.get(), this)) {
        _dtmf->UnregisterObserver();
      }
    });
  }

  void RTCDTMFSender::Init(pybind11::module &m) {
    DefineBinding(pybind11::class_<RTCDTMFSender, Binding, std::shared_ptr<RTCDTMFSender>>(m, "RTCDTMFSender"))
        .def_property_readonly("_id", &RTCDTMFSender::Id)
        .def_property_readonly("toneBuffer", nogil_fn(&RTCDTMFSender::GetToneBuffer))
        .def_property_readonly("canInsertDTMF", nogil_fn(&RTCDTMFSender::GetCanInsertDtmf))
        .def("_checkCanSend", &RTCDTMFSender::CheckCanSend, nogil())
        .def("insertDTMF", &RTCDTMFSender::InsertDtmf, nogil(), pybind11::arg("tones"), pybind11::arg("duration"),
             pybind11::arg("interToneGap"))
        .def("_surfaceBuffer", &RTCDTMFSender::SurfaceBuffer, nogil(), pybind11::arg("buffer"),
             pybind11::arg("insertion"), pybind11::arg("ended"))
        .def_property_readonly("_playing", nogil_fn(&RTCDTMFSender::GetPlaying));
  }

  Registry<RTCDTMFSender, webrtc::DtmfSenderInterface> &RTCDTMFSender::registry() {
    static ForkLocal<Registry<RTCDTMFSender, webrtc::DtmfSenderInterface>> registry;
    return registry.Get();
  }

  void RTCDTMFSender::SetTransceiverState(std::function<TransceiverState()> state) {
    _transceiverState.Set(std::move(state));
  }

  void RTCDTMFSender::OnToneChange(const std::string &tone, const std::string &toneBuffer) {
    uint64_t insertion = 0;
    {
      const std::scoped_lock lock(_bufferMutex);
      insertion = _insertions;
    }
    Emit("tonechange", tone, toneBuffer, insertion);
  }

  std::optional<std::string> RTCDTMFSender::CannotSend() {
    auto lookup = _transceiverState.Get();
    auto state = lookup ? lookup() : TransceiverState::Gone();
    if (state.stopping || state.stopped) {
      return "The transceiver of the sender is stopped";
    }
    auto direction = state.currentDirection;
    if (direction && (*direction == webrtc::RtpTransceiverDirection::kRecvOnly ||
                      *direction == webrtc::RtpTransceiverDirection::kInactive)) {
      return "The transceiver of the sender doesn't send";
    }
    if (!_dtmf->CanInsertDtmf()) {
      return "The DTMF sender can't send tones yet";
    }
    return std::nullopt;
  }

  void RTCDTMFSender::CheckCanSend() {
    if (auto reason = CannotSend()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, *reason);
    }
  }

  void RTCDTMFSender::InsertDtmf(const std::string &tones, int duration, int interToneGap) {
    // the proxies run inline there; nothing may throw through libwebrtc's task
    auto reason = BlockingCallOn(_factory->signalingThread(), [&]() -> std::optional<std::string> {
      auto cannot = CannotSend();
      if (cannot || (tones.empty() && _dtmf->tones().empty())) {
        // or nothing to play, nor to cancel
        return cannot;
      }
      {
        // tone changes of the tones inserted before don't change the buffer anymore
        const std::scoped_lock lock(_bufferMutex);
        ++_insertions;
      }
      if (!_dtmf->InsertDtmf(tones, duration, interToneGap) && !tones.empty()) {
        return "The DTMF sender can't send tones yet";
      }
      const std::scoped_lock lock(_bufferMutex);
      _surfacedBuffer = tones;
      // a cancel (no tones) ends with an empty tonechange too
      _playing = true;
      return std::nullopt;
    });
    if (reason) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, *reason);
    }
  }

  std::string RTCDTMFSender::GetToneBuffer() {
    {
      const std::scoped_lock lock(_bufferMutex);
      if (IsBound() && _surfacedBuffer) {
        return *_surfacedBuffer;
      }
    }
    return _dtmf->tones();
  }

  void RTCDTMFSender::SurfaceBuffer(const std::string &buffer, uint64_t insertion, bool ended) {
    const std::scoped_lock lock(_bufferMutex);
    // a tone played before the last insertDTMF() doesn't change what it set
    if (insertion == _insertions) {
      _surfacedBuffer = buffer;
      if (ended) {
        _playing = false;
      }
    }
  }

  bool RTCDTMFSender::GetPlaying() {
    const std::scoped_lock lock(_bufferMutex);
    return _playing;
  }

  bool RTCDTMFSender::GetCanInsertDtmf() {
    return _dtmf->CanInsertDtmf();
  }

} // namespace python_webrtc
