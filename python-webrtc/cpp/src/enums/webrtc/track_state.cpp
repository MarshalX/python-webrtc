//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "track_state.h"

#include <api/media_stream_interface.h>

namespace python_webrtc {

  void TrackState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::MediaStreamTrackInterface::TrackState>(m, "MediaStreamTrackState")
        .value("live", webrtc::MediaStreamTrackInterface::TrackState::kLive)
        .value("ended", webrtc::MediaStreamTrackInterface::TrackState::kEnded)
        .export_values();
  }

}
