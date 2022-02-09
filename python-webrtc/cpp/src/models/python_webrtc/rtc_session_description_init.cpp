//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_session_description_init.h"

namespace python_webrtc {

  RTCSessionDescriptionInit::RTCSessionDescriptionInit() {}

  RTCSessionDescriptionInit::RTCSessionDescriptionInit(webrtc::SdpType type, std::string sdp) :
      type(type), sdp(std::move(sdp)) {}

  void RTCSessionDescriptionInit::Init(pybind11::module &m) {
    pybind11::class_<RTCSessionDescriptionInit>(m, "RTCSessionDescriptionInit")
        .def(pybind11::init<webrtc::SdpType, std::string>())
        .def_readwrite("type", &RTCSessionDescriptionInit::type)
        .def_readwrite("sdp", &RTCSessionDescriptionInit::sdp);
  }

  RTCSessionDescriptionInit RTCSessionDescriptionInit::Wrap(webrtc::SessionDescriptionInterface *description) {
    std::string sdp;
    description->ToString(&sdp);

    return RTCSessionDescriptionInit(description->GetType(), sdp);
  }

}
