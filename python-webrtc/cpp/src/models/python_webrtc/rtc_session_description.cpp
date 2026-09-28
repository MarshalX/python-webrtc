//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_session_description.h"

namespace python_webrtc {

  RTCSessionDescription::RTCSessionDescription(const RTCSessionDescriptionInit &init) : _init(init) {}

  webrtc::SdpType RTCSessionDescription::getType() {
    return _init.type;
  }

  std::string RTCSessionDescription::getSdp() {
    return _init.sdp;
  }

  void RTCSessionDescription::Init(pybind11::module &m) {
    pybind11::class_<RTCSessionDescription, std::shared_ptr<RTCSessionDescription>>(m, "RTCSessionDescription")
        .def(pybind11::init<const RTCSessionDescriptionInit &>())
        .def_property_readonly("type", &RTCSessionDescription::getType)
        .def_property_readonly("sdp", &RTCSessionDescription::getSdp)
        .def_property_readonly("init", &RTCSessionDescription::init);
  }

  RTCSessionDescription RTCSessionDescription::Wrap(webrtc::SessionDescriptionInterface *description) {
    return RTCSessionDescription(RTCSessionDescriptionInit::Wrap(description));
  }

} // namespace python_webrtc
