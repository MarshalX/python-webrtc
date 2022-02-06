//
// Created by Il'ya Semyonov on 1/11/22.
//

#include "rtc_rtp_sender.h"

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(PeerConnectionFactory *factory, webrtc::RtpSenderInterface *sender)
      : _factory(factory), _sender(sender) {}

  RTCRtpSender::~RTCRtpSender() {
    _factory = nullptr;
  }

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender>(m, "RTCRtpSender")
        .def_property_readonly("track", &RTCRtpSender::GetTrack);
  }

  std::optional<std::unique_ptr<MediaStreamTrack>> RTCRtpSender::GetTrack() {
    auto track = _sender->track();
    if (track) {
      // TODO should be getOrCreate? because we can get the same track from stream.getTracks(), for example
      // shared ptr?
      return std::make_unique<MediaStreamTrack>(_factory, track);
    }

    return {};
  }

}
