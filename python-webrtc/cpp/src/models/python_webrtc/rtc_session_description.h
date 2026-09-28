//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include "rtc_session_description_init.h"

namespace python_webrtc {

  class RTCSessionDescription {
  public:
    // TODO rtcSessionDescriptionInit should be optional
    // https://github.com/MarshalX/python-webrtc/issues/171
    explicit RTCSessionDescription(const RTCSessionDescriptionInit &rtcSessionDescriptionInit);

    static void Init(pybind11::module &m);

    static RTCSessionDescription Wrap(webrtc::SessionDescriptionInterface *);

    [[nodiscard]] const RTCSessionDescriptionInit &init() const { return _init; }

    webrtc::SdpType getType();

    std::string getSdp();

  private:
    // not parsed: an invalid description is only rejected when it's set
    RTCSessionDescriptionInit _init;
  };

} // namespace python_web_rtc
