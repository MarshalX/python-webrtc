//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "dtls_transport_state.h"

#include <api/dtls_transport_interface.h>

namespace python_webrtc {

  void DtlsTransportState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::DtlsTransportState>(m, "DtlsTransportState")
        .value("new", webrtc::DtlsTransportState::kNew)
        .value("connecting", webrtc::DtlsTransportState::kConnecting)
        .value("connected", webrtc::DtlsTransportState::kConnected)
        .value("closed", webrtc::DtlsTransportState::kClosed)
        .value("failed", webrtc::DtlsTransportState::kFailed)
        .export_values();
  }

} // namespace python_webrtc
