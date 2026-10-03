//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "models.h"

#include "python_webrtc/rtc_certificate.h"
#include "python_webrtc/rtc_configuration.h"
#include "python_webrtc/rtc_ice_candidate.h"
#include "python_webrtc/rtc_session_description.h"

#include "webrtc/rtp_parameters.h"
#include "webrtc/rtp_transceiver_init.h"

namespace python_webrtc {

  void Models::Init(pybind11::module &m) {
    RTCSessionDescriptionInit::Init(m);
    RTCSessionDescription::Init(m);
    RTCIceCandidate::Init(m);
    RTCCertificate::Init(m);
    ConfigurationInit::Init(m);

    bindRtpParameters(m);
    bindRtpTransceiverInit(m);
  }
} // namespace python_webrtc
