//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "sdp_type.h"

#include <webrtc/api/jsep.h>

namespace python_webrtc {

  void SdpType::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::SdpType>(m, "RTCSdpType")
        .value("offer", webrtc::SdpType::kOffer)
        .value("pranswer", webrtc::SdpType::kPrAnswer)
        .value("answer", webrtc::SdpType::kAnswer)
        .value("rollback", webrtc::SdpType::kRollback)
        .export_values();
  }

}
