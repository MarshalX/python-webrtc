//
// Created by Il'ya Semyonov on 1/8/22.
//

#include "rtc_session_description.h"

namespace python_webrtc {

  RTCSessionDescription::RTCSessionDescription(const RTCSessionDescriptionInit &init) {
    webrtc::SdpParseError error;
    auto description = webrtc::CreateSessionDescription(init.type, init.sdp, &error);
    if (!description) {
      // TODO
    }

    _description = std::move(description);
  }

  webrtc::SdpType RTCSessionDescription::getType() {
    return _description->GetType();
  }

  std::string RTCSessionDescription::getSdp() {
    std::string sdp;
    _description->ToString(&sdp);
    return sdp;
  }

  void RTCSessionDescription::Init(pybind11::module &m) {
    pybind11::class_<RTCSessionDescription>(m, "RTCSessionDescription")
        .def(pybind11::init<const RTCSessionDescriptionInit&>())
        .def_property_readonly("type", &RTCSessionDescription::getType)
        .def_property_readonly("sdp", &RTCSessionDescription::getSdp);
  }

  RTCSessionDescription::operator webrtc::SessionDescriptionInterface*() {
    // TODO update mb when will be necessary
    return _description.get();
  }

  RTCSessionDescription RTCSessionDescription::Wrap(webrtc::SessionDescriptionInterface *description) {
    return RTCSessionDescription(RTCSessionDescriptionInit::Wrap(description));
  }

} // namespace python_webrtc
