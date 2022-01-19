//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "models.h"

#include "python_webrtc/rtc_session_description.h"
#include "python_webrtc/rtc_on_data_event.h"

namespace python_webrtc {

  void Models::Init(pybind11::module &m) {
    // python_webrtc

    RTCSessionDescriptionInit::Init(m);
    RTCSessionDescription::Init(m);
    RTCOnDataEvent::Init(m);

    // webrtc
  }
}
