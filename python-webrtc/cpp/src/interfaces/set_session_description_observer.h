//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include "rtc_peer_connection.h"

namespace webrtc { class RTCError; }

namespace python_webrtc {

  class SetSessionDescriptionObserver : public webrtc::SetSessionDescriptionObserver {
  public:
    SetSessionDescriptionObserver(
        std::function<void()> &onSuccess,
        std::function<void(CallbackPythonWebRTCException)> &onFailure) :
        _onSuccess(onSuccess), _onFailure(onFailure) {}

    void OnSuccess() override;

    void OnFailure(webrtc::RTCError) override;

  private:
    std::function<void()> _onSuccess = nullptr;
    std::function<void(CallbackPythonWebRTCException)> _onFailure = nullptr;
  };

} // namespace python_webrtc
