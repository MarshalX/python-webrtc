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
    explicit RTCSessionDescription(const RTCSessionDescriptionInit &rtcSessionDescriptionInit);

    static void Init(pybind11::module &m);

    static RTCSessionDescription Wrap(webrtc::SessionDescriptionInterface *);

    explicit operator webrtc::SessionDescriptionInterface *();

    webrtc::SdpType getType();

    std::string getSdp();

    // TODO .toJSON() method?
  private:
    std::unique_ptr<webrtc::SessionDescriptionInterface> _description;
  };

} // namespace python_web_rtc
