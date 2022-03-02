//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtp_transceiver_direction.h"

#include <api/rtp_transceiver_direction.h>

namespace python_webrtc {

  void RTPTransceiverDirection::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::RtpTransceiverDirection>(m, "TransceiverDirection")
        .value("sendrecv", webrtc::RtpTransceiverDirection::kSendRecv)
        .value("sendonly", webrtc::RtpTransceiverDirection::kSendOnly)
        .value("recvonly", webrtc::RtpTransceiverDirection::kRecvOnly)
        .value("inactive", webrtc::RtpTransceiverDirection::kInactive)
        .value("stopped", webrtc::RtpTransceiverDirection::kStopped)
        .export_values();
  }

} // namespace python_webrtc
