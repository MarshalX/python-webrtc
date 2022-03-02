//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_transceiver.h"
#include "../exceptions.h"

namespace python_webrtc {

  RTCRtpTransceiver::RTCRtpTransceiver(PeerConnectionFactory *factory,
                                       rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) : _factory(
      factory), _transceiver(std::move(transceiver)) {}

  RTCRtpTransceiver::~RTCRtpTransceiver() {
    _factory == nullptr;
    holder()->Release(this);
  }

  void RTCRtpTransceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpTransceiver>(m, "RTCRtpTransceiver")
        .def_property_readonly("mid", &RTCRtpTransceiver::GetMid)
        .def_property_readonly("sender", &RTCRtpTransceiver::GetSender, pybind11::return_value_policy::reference)
        .def_property_readonly("receiver", &RTCRtpTransceiver::GetReceiver, pybind11::return_value_policy::reference)
        .def_property_readonly("stopped", &RTCRtpTransceiver::GetStopped)
        .def_property("direction", &RTCRtpTransceiver::GetDirection, &RTCRtpTransceiver::SetDirection)
        .def_property_readonly("currentDirection", &RTCRtpTransceiver::GetCurrentDirection)
            // set codec pref
        .def("stop", &RTCRtpTransceiver::Stop);
  }

  InstanceHolder<RTCRtpTransceiver *, rtc::scoped_refptr<webrtc::RtpTransceiverInterface>, PeerConnectionFactory *> *
  RTCRtpTransceiver::holder() {
    static auto holder = new InstanceHolder<
        RTCRtpTransceiver *, rtc::scoped_refptr<webrtc::RtpTransceiverInterface>, PeerConnectionFactory *
    >(RTCRtpTransceiver::Create);
    return holder;
  }

  RTCRtpTransceiver *RTCRtpTransceiver::Create(PeerConnectionFactory *factory,
                                               rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
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
