//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "source_state.h"

#include <api/media_stream_interface.h>

namespace python_webrtc {

  void SourceState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::MediaSourceInterface::SourceState>(m, "MediaStreamSourceState")
        .value("initializing", webrtc::MediaSourceInterface::SourceState::kInitializing)
        .value("live", webrtc::MediaSourceInterface::SourceState::kLive)
        .value("ended", webrtc::MediaSourceInterface::SourceState::kEnded)
        .value("muted", webrtc::MediaSourceInterface::SourceState::kMuted)
        .export_values();
  }

}
