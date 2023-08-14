//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "cricket_ice_gathering_state.h"

#include <p2p/base/ice_transport_internal.h>

namespace python_webrtc {

  void CricketIceGatheringState::Init(pybind11::module &m) {
    pybind11::enum_<cricket::IceGatheringState>(m, "CricketIceGatheringState")
        .value("new", cricket::IceGatheringState::kIceGatheringNew)
        .value("gathering", cricket::IceGatheringState::kIceGatheringGathering)
        .value("complete", cricket::IceGatheringState::kIceGatheringComplete)
        .export_values();
  }

} // namespace python_webrtc
