//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "sdp_type.h"

#include <webrtc/api/jsep.h>

namespace python_webrtc {

  void SdpType::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::SdpType>(m,"RTCSdpType")
        .value("offer", webrtc::SdpType::kOffer)
        .value("pranswer", webrtc::SdpType::kPrAnswer)
        .value("answer", webrtc::SdpType::kAnswer)
        .value("rollback", webrtc::SdpType::kRollback)
        .export_values();
  }

}
