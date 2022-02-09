//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_session_description.h"

namespace python_webrtc {

  RTCSessionDescription::RTCSessionDescription(const RTCSessionDescriptionInit &init) {
    webrtc::SdpParseError error;
    auto description = webrtc::CreateSessionDescription(init.type, init.sdp, &error);
    if (!description) {
      // TODO throw exception with error
    }

    _description = std::move(description);
  }

  webrtc::SdpType RTCSessionDescription::getType() {
    return _description->GetType();
  }

  std::string RTCSessionDescription::getSdp() {
    std::string sdp;
    _description->ToString(&sdp);
    return sdp;
  }

  void RTCSessionDescription::Init(pybind11::module &m) {
    pybind11::class_<RTCSessionDescription>(m, "RTCSessionDescription")
        .def(pybind11::init<const RTCSessionDescriptionInit &>())
        .def_property_readonly("type", &RTCSessionDescription::getType)
        .def_property_readonly("sdp", &RTCSessionDescription::getSdp);
  }

  RTCSessionDescription::operator webrtc::SessionDescriptionInterface *() {
    return webrtc::CreateSessionDescription(this->getType(), this->getSdp()).release();
  }

  RTCSessionDescription RTCSessionDescription::Wrap(webrtc::SessionDescriptionInterface *description) {
    return RTCSessionDescription(RTCSessionDescriptionInit::Wrap(description));
  }

} // namespace python_webrtc
