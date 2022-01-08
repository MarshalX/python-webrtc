//
// Created by Il'ya Semyonov on 1/6/22.
//

#pragma once

#include "rtc_peer_connection.h"

namespace webrtc { class RTCError; }

namespace python_webrtc {

  class CreateSessionDescriptionObserver : public webrtc::CreateSessionDescriptionObserver {
  public:
    explicit CreateSessionDescriptionObserver(RTCPeerConnection* peer_connection, std::function<void(RTCSessionDescription)> &on_success);

    void OnSuccess(webrtc::SessionDescriptionInterface*) override;

    void OnFailure(webrtc::RTCError) override;

  private:
    RTCPeerConnection* _peer_connection;
    std::function<void(RTCSessionDescription)> _on_success = nullptr;
    std::function<void(std::string)> _on_error = nullptr;
  };

} // namespace python_webrtc
