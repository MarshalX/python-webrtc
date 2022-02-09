//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
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

    static RTCSessionDescriptionInit Wrap(webrtc::SessionDescriptionInterface *);

    webrtc::SdpType type;
    std::string sdp;
  };

} //namespace python_webrtc
