//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include <api/peer_connection_interface.h>

#include "ice_gathering_state.h"

namespace python_webrtc {

  void IceGatheringState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::PeerConnectionInterface::IceGatheringState>(m, "RTCIceGatheringState")
        .value("new", webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringNew)
        .value("gathering", webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringGathering)
        .value("complete", webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringComplete)
        .export_values();
  }

}
