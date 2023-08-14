//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "sctp_transport_state.h"

#include <api/sctp_transport_interface.h>

namespace python_webrtc {

  void SctpTransportState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::SctpTransportState>(m, "SctpTransportState")
        .value("new", webrtc::SctpTransportState::kNew)
        .value("connecting", webrtc::SctpTransportState::kConnecting)
        .value("connected", webrtc::SctpTransportState::kConnected)
        .value("closed", webrtc::SctpTransportState::kClosed)
//        .value("numvalues", webrtc::SctpTransportState::kNumValues) // not used
        .export_values();
  }

} // namespace python_webrtc
