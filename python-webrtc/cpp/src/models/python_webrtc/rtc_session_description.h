//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_H_
#define PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_H_

#include "rtc_session_description_init.h"

namespace python_webrtc {

  class RTCSessionDescription {
  public:
    // the init is required, as in the specification: its sdp is empty by default
    explicit RTCSessionDescription(RTCSessionDescriptionInit init);

    static void Init(pybind11::module &m);

    static RTCSessionDescription Wrap(webrtc::SessionDescriptionInterface *description);

    [[nodiscard]] const RTCSessionDescriptionInit &init() const { return _init; }

    [[nodiscard]] webrtc::SdpType getType() const;

    [[nodiscard]] std::string getSdp() const;

  private:
    // not parsed: an invalid description is only rejected when it's set
    RTCSessionDescriptionInit _init;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_SESSION_DESCRIPTION_H_
