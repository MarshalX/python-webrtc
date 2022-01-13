//
// Created by Il'ya Semyonov on 1/11/22.
//

#include "rtc_rtp_sender.h"

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(factory), _sender(std::move(sender)) {}

  RTCRtpSender::~RTCRtpSender() {
    _factory = nullptr;
  }

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender>(m, "RTCRtpSender")
        .def_property_readonly("track", &RTCRtpSender::GetTrack);
  }

  std::optional<MediaStreamTrack> RTCRtpSender::GetTrack() {
    auto track = _sender->track();
    if (track) {
      return MediaStreamTrack(_factory, track);
    }

    return {};
  }

}
