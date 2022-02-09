//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
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
