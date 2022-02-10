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

  class CreateSessionDescriptionObserver : public webrtc::CreateSessionDescriptionObserver {
  public:
    CreateSessionDescriptionObserver(RTCPeerConnection *peerConnection,
                                     std::function<void(RTCSessionDescription)> &onSuccess,
                                     std::function<void(CallbackPythonWebRTCException)> &onFailure) :
        _peerConnection(peerConnection), _onSuccess(onSuccess), _onFailure(onFailure) {}

    void OnSuccess(webrtc::SessionDescriptionInterface *) override;

    void OnFailure(webrtc::RTCError) override;

  private:
    RTCPeerConnection *_peerConnection;
    std::function<void(RTCSessionDescription)> _onSuccess = nullptr;
    std::function<void(CallbackPythonWebRTCException)> _onFailure = nullptr;
  };

} // namespace python_webrtc
