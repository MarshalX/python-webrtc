//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "source_state.h"

#include <api/media_stream_interface.h>

namespace python_webrtc {

  void SourceState::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::MediaSourceInterface::SourceState>(m,"MediaStreamSourceState")
        .value("initializing", webrtc::MediaSourceInterface::SourceState::kInitializing)
        .value("live", webrtc::MediaSourceInterface::SourceState::kLive)
        .value("ended", webrtc::MediaSourceInterface::SourceState::kEnded)
        .value("muted", webrtc::MediaSourceInterface::SourceState::kMuted)
        .export_values();
  }

}
