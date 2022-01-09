//
// Created by Il'ya Semyonov on 1/6/22.
//

#pragma once

#include "rtc_peer_connection.h"

namespace webrtc { class RTCError; }

namespace python_webrtc {

  class SetSessionDescriptionObserver : public webrtc::SetSessionDescriptionObserver {
  public:
    explicit SetSessionDescriptionObserver(std::function<void()> &on_success): _on_success(on_success) {}

    void OnSuccess() override;

    void OnFailure(webrtc::RTCError) override;

  private:
    std::function<void()> _on_success = nullptr;
    std::function<void(std::string)> _on_error = nullptr;
  };

} // namespace python_webrtc
