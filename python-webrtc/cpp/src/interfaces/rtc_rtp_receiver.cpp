//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_receiver.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCRtpReceiver::RTCRtpReceiver(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver
  ) : _factory(std::move(factory)), _receiver(std::move(receiver)) {}

  void RTCRtpReceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpReceiver, std::shared_ptr<RTCRtpReceiver>>(m, "RTCRtpReceiver")
        .def_property_readonly("track", nogil_fn(&RTCRtpReceiver::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpReceiver::GetTransport));
  }

  InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &RTCRtpReceiver::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface>();
    return *holder;
  }

  std::shared_ptr<MediaStreamTrack> RTCRtpReceiver::GetTrack() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_track) {
      _track = MediaStreamTrack::holder().GetOrCreate(_factory, _receiver->track());
    }
    return _track;
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpReceiver::GetTransport() {
    auto transport = _receiver->dtls_transport();

    std::shared_ptr<RTCDtlsTransport> previous;
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_transport || _transport->transport() != transport) {
      previous = std::move(_transport);
      _transport = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);
    }

    if (_transport) {
      return _transport;
    }
    return {};
  }

} // namespace python_webrtc
