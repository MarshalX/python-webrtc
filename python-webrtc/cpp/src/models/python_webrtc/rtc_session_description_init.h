//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_INIT_H_
#define PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_INIT_H_

#include <string>

#include <api/jsep.h>
#include <pybind11/pybind11.h>

#include "../../enums/enums.h"

namespace python_webrtc {

  class RTCSessionDescriptionInit {
  public:
    RTCSessionDescriptionInit();

    RTCSessionDescriptionInit(webrtc::SdpType type, std::string sdp);

    static void Init(pybind11::module &m);

    static RTCSessionDescriptionInit Wrap(const webrtc::SessionDescriptionInterface *description);

    webrtc::SdpType type{};
    std::string sdp;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_INIT_H_
