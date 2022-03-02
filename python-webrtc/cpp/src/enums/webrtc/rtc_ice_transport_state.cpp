//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_transport_state.h"

#include <api/transport/enums.h>

namespace python_webrtc {

  void RTCIceTransportState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::IceTransportState>(m, "RTCIceTransportState")
        .value("new", webrtc::IceTransportState::kNew)
        .value("checking", webrtc::IceTransportState::kChecking)
        .value("connected", webrtc::IceTransportState::kConnected)
        .value("completed", webrtc::IceTransportState::kCompleted)
        .value("disconnected", webrtc::IceTransportState::kDisconnected)
        .value("failed", webrtc::IceTransportState::kFailed)
        .value("closed", webrtc::IceTransportState::kClosed)
        .export_values();
  }

} // namespace python_webrtc
