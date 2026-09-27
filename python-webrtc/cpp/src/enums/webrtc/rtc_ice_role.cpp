//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_role.h"

#include <p2p/base/transport_description.h>

namespace python_webrtc {

  void RTCIceRole::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::IceRole>(m, "RTCIceRole")
        .value("controlling", webrtc::IceRole::ICEROLE_CONTROLLING)
        .value("controlled", webrtc::IceRole::ICEROLE_CONTROLLED)
        .value("unknown", webrtc::IceRole::ICEROLE_UNKNOWN) // not standard? should not be occurred?
        .export_values();
  }

} // namespace python_webrtc
