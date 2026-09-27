//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_transceiver.h"
#include "../utils/gil.h"
#include "../exceptions.h"

namespace python_webrtc {

  RTCRtpTransceiver::RTCRtpTransceiver(PeerConnectionFactory *factory,
                                       webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) : _factory(
      factory), _transceiver(std::move(transceiver)) {}

  RTCRtpTransceiver::~RTCRtpTransceiver() {
    _factory == nullptr;
    holder()->Release(this);
  }

  void RTCRtpTransceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpTransceiver>(m, "RTCRtpTransceiver")
        .def_property_readonly("mid", nogil_fn(&RTCRtpTransceiver::GetMid))
        .def_property_readonly("sender", nogil_fn(&RTCRtpTransceiver::GetSender), pybind11::return_value_policy::reference)
        .def_property_readonly("receiver", nogil_fn(&RTCRtpTransceiver::GetReceiver), pybind11::return_value_policy::reference)
        .def_property_readonly("stopped", nogil_fn(&RTCRtpTransceiver::GetStopped))
        .def_property("direction", nogil_fn(&RTCRtpTransceiver::GetDirection), nogil_fn(&RTCRtpTransceiver::SetDirection))
        .def_property_readonly("currentDirection", nogil_fn(&RTCRtpTransceiver::GetCurrentDirection))
            // set codec pref
        .def("stop", &RTCRtpTransceiver::Stop, nogil());
  }

  InstanceHolder<RTCRtpTransceiver *, webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>, PeerConnectionFactory *> *
  RTCRtpTransceiver::holder() {
    static auto holder = new InstanceHolder<
        RTCRtpTransceiver *, webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>, PeerConnectionFactory *
    >(RTCRtpTransceiver::Create);
    return holder;
  }

  RTCRtpTransceiver *RTCRtpTransceiver::Create(PeerConnectionFactory *factory,
                                               webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
    // who caring about freeing memory?
    return new RTCRtpTransceiver(factory, std::move(transceiver));
  }

  std::optional<std::string> RTCRtpTransceiver::GetMid() {
    if (_transceiver->mid()) {
      return _transceiver->mid().value();
    }

    return {};
  }

  RTCRtpSender *RTCRtpTransceiver::GetSender() {
    return RTCRtpSender::holder()->GetOrCreate(_factory, _transceiver->sender());
  }

  RTCRtpReceiver *RTCRtpTransceiver::GetReceiver() {
    return RTCRtpReceiver::holder()->GetOrCreate(_factory, _transceiver->receiver());
  }

  bool RTCRtpTransceiver::GetStopped() {
    // TODO Deprecated: This feature is no longer recommended.
    return _transceiver->stopped();
  }

  webrtc::RtpTransceiverDirection RTCRtpTransceiver::GetDirection() {
    return _transceiver->direction();
  }

  void RTCRtpTransceiver::SetDirection(webrtc::RtpTransceiverDirection direction) {
    auto result = _transceiver->SetDirectionWithError(direction);
    if (!result.ok()) {
      throw wrapRTCError(result);
    }
  }

  std::optional<webrtc::RtpTransceiverDirection> RTCRtpTransceiver::GetCurrentDirection() {
    if (_transceiver->current_direction()) {
      return _transceiver->current_direction().value();
    }

    return {};
  }

  void RTCRtpTransceiver::Stop() {
    auto result = _transceiver->StopStandard();
    if (!result.ok()) {
      throw wrapRTCError(result);
    }
  }

} // namespace python_webrtc
