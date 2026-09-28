//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_sender.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(std::move(factory)), _sender(std::move(sender)) {}

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender, std::shared_ptr<RTCRtpSender>>(m, "RTCRtpSender")
        .def_property_readonly("track", nogil_fn(&RTCRtpSender::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpSender::GetTransport));
  }

  InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &RTCRtpSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface>();
    return *holder;
  }

  std::optional<std::shared_ptr<MediaStreamTrack>> RTCRtpSender::GetTrack() {
    auto track = _sender->track();

    std::shared_ptr<MediaStreamTrack> previous;
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_track || _track->track() != track) {
      previous = std::move(_track);
      _track = MediaStreamTrack::holder().GetOrCreate(_factory, track);
    }

    if (_track) {
      return _track;
    }
    return {};
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpSender::GetTransport() {
    auto transport = _sender->dtls_transport();

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
