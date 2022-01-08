//
// Created by Il'ya Semyonov on 1/8/22.
//

#pragma once

#include "rtc_session_description_init.h"

namespace python_webrtc {

  class RTCSessionDescription {
  public:
    // TODO rtcSessionDescriptionInit should be optional
    explicit RTCSessionDescription(const RTCSessionDescriptionInit& rtcSessionDescriptionInit);

    static void Init(pybind11::module &m);
    static RTCSessionDescription Wrap(webrtc::SessionDescriptionInterface*);

    explicit operator webrtc::SessionDescriptionInterface*();

    webrtc::SdpType getType();
    std::string getSdp();

    // TODO .toJSON() method?
  private:
    std::unique_ptr<webrtc::SessionDescriptionInterface> _description;
  };

} // namespace python_web_rtc
