//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_receiver.h"

namespace python_webrtc {

  RTCRtpReceiver::RTCRtpReceiver(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver
  ) : _factory(factory), _receiver(std::move(receiver)) {}

  RTCRtpReceiver::~RTCRtpReceiver() {
    _factory = nullptr;
    holder()->Release(this);
  }

  void RTCRtpReceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpReceiver>(m, "RTCRtpReceiver")
        .def_property_readonly("track", &RTCRtpReceiver::GetTrack, pybind11::return_value_policy::reference)
        .def_property_readonly("transport", &RTCRtpReceiver::GetTransport);
  }

  InstanceHolder<RTCRtpReceiver *, rtc::scoped_refptr<webrtc::RtpReceiverInterface>, PeerConnectionFactory *> *
  RTCRtpReceiver::holder() {
    static auto holder = new InstanceHolder<
        RTCRtpReceiver *, rtc::scoped_refptr<webrtc::RtpReceiverInterface>, PeerConnectionFactory *
    >(RTCRtpReceiver::Create);
    return holder;
  }

  RTCRtpReceiver *RTCRtpReceiver::Create(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {
    // who caring about freeing memory?
    return new RTCRtpReceiver(factory, std::move(receiver));
  }

  MediaStreamTrack *RTCRtpReceiver::GetTrack() {
    return MediaStreamTrack::holder()->GetOrCreate(_factory, _receiver->track());
  }

  std::optional<RTCDtlsTransport *> RTCRtpReceiver::GetTransport() {
    auto transport = _receiver->dtls_transport();
    if (transport) {
      return RTCDtlsTransport::holder()->GetOrCreate(_factory, transport);
    }

    return {};
  }

} // namespace python_webrtc
