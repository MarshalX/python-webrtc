//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "track_state.h"

#include <api/media_stream_interface.h>

namespace python_webrtc {

  void TrackState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::MediaStreamTrackInterface::TrackState>(m,"MediaStreamTrackState")
        .value("live", webrtc::MediaStreamTrackInterface::TrackState::kLive)
        .value("ended", webrtc::MediaStreamTrackInterface::TrackState::kEnded)
        .export_values();
  }

}
