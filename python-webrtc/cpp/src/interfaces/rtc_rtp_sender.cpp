//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_sender.h"

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(factory), _sender(std::move(sender)) {}

  RTCRtpSender::~RTCRtpSender() {
    _factory = nullptr;

    holder()->Release(this);
  }

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender>(m, "RTCRtpSender")
        .def_property_readonly("track", &RTCRtpSender::GetTrack);
  }

  std::optional<MediaStreamTrack *> RTCRtpSender::GetTrack() {
    auto track = _sender->track();
    if (track) {
      return MediaStreamTrack::holder()->GetOrCreate(_factory, track);
    }

    return {};
  }

  InstanceHolder<RTCRtpSender *, rtc::scoped_refptr<webrtc::RtpSenderInterface>, PeerConnectionFactory *> *
  RTCRtpSender::holder() {
    static auto holder = new InstanceHolder<
        RTCRtpSender *, rtc::scoped_refptr<webrtc::RtpSenderInterface>, PeerConnectionFactory *
    >(RTCRtpSender::Create);
    return holder;
  }

  RTCRtpSender *RTCRtpSender::Create(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::RtpSenderInterface> sender
  ) {
    // who caring about freeing memory?
    return new RTCRtpSender(factory, std::move(sender));
  }

}
