//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_component.h"


namespace python_webrtc {

  void RTCIceComponent_::Init(pybind11::module &m) {
    pybind11::enum_<RTCIceComponent>(m, "RTCIceComponent")
        .value("RTP", RTCIceComponent::kRtp)
        .value("RTCP", RTCIceComponent::kRtcp)
        .export_values();
  }

} // namespace python_webrtc
