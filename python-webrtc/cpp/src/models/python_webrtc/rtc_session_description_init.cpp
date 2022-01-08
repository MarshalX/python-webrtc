//
// Created by Il'ya Semyonov on 1/8/22.
//

#include "rtc_session_description_init.h"

namespace python_webrtc {

  RTCSessionDescriptionInit::RTCSessionDescriptionInit() {}

  RTCSessionDescriptionInit::RTCSessionDescriptionInit(webrtc::SdpType type, std::string sdp):
    type(type), sdp(std::move(sdp)) {}

  void RTCSessionDescriptionInit::Init(pybind11::module &m) {
    pybind11::class_<RTCSessionDescriptionInit>(m, "RTCSessionDescriptionInit")
        .def(pybind11::init<webrtc::SdpType, std::string>())
        .def_readwrite("type", &RTCSessionDescriptionInit::type)
        .def_readwrite("sdp", &RTCSessionDescriptionInit::sdp);
  }

  RTCSessionDescriptionInit RTCSessionDescriptionInit::Wrap(webrtc::SessionDescriptionInterface *description) {
    std::string sdp;
    description->ToString(&sdp);

    return RTCSessionDescriptionInit(description->GetType(), sdp);
  }

}
