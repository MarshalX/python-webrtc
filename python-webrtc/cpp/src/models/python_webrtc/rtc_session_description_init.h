//
// Created by Il'ya Semyonov on 1/8/22.
//

#pragma once

#include <string>

#include <webrtc/api/jsep.h>
#include <pybind11/pybind11.h>

namespace python_webrtc {

  class RTCSessionDescriptionInit {
  public:
    // TODO sdp should be optional (empty string by default) and not None
    RTCSessionDescriptionInit();
    RTCSessionDescriptionInit(webrtc::SdpType type, std::string sdp);

    static void Init(pybind11::module &m);
    static RTCSessionDescriptionInit Wrap(webrtc::SessionDescriptionInterface*);

    webrtc::SdpType type;
    std::string sdp;
  };

} //namespace python_webrtc
