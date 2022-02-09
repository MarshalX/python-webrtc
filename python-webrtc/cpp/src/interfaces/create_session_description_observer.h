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
    explicit CreateSessionDescriptionObserver(RTCPeerConnection *peer_connection,
                                              std::function<void(RTCSessionDescription)> &on_success);

    void OnSuccess(webrtc::SessionDescriptionInterface *) override;

    void OnFailure(webrtc::RTCError) override;

  private:
    RTCPeerConnection *_peer_connection;
    std::function<void(RTCSessionDescription)> _on_success = nullptr;
    std::function<void(std::string)> _on_error = nullptr;
  };

} // namespace python_webrtc
