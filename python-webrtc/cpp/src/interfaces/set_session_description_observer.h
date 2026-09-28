//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include "rtc_peer_connection.h"

#include <api/set_local_description_observer_interface.h>
#include <api/set_remote_description_observer_interface.h>

namespace webrtc { class RTCError; }

namespace python_webrtc {

  class SetSessionDescriptionObserver : public webrtc::SetSessionDescriptionObserver {
  public:
    SetSessionDescriptionObserver(
        std::function<void()> &onSuccess,
        std::function<void(RTCCallbackException)> &onFailure) :
        _onSuccess(onSuccess), _onFailure(onFailure) {}

    void OnSuccess() override;

    void OnFailure(webrtc::RTCError) override;

  private:
    std::function<void()> _onSuccess = nullptr;
    std::function<void(RTCCallbackException)> _onFailure = nullptr;
  };

  // Completion of SetLocalDescription/SetRemoteDescription, called on the signaling thread
  class SetLocalDescriptionObserver : public webrtc::SetLocalDescriptionObserverInterface {
  public:
    explicit SetLocalDescriptionObserver(std::function<void(webrtc::RTCError)> onComplete)
        : _onComplete(std::move(onComplete)) {}

    void OnSetLocalDescriptionComplete(webrtc::RTCError error) override { _onComplete(std::move(error)); }

  private:
    std::function<void(webrtc::RTCError)> _onComplete;
  };

  class SetRemoteDescriptionObserver : public webrtc::SetRemoteDescriptionObserverInterface {
  public:
    explicit SetRemoteDescriptionObserver(std::function<void(webrtc::RTCError)> onComplete)
        : _onComplete(std::move(onComplete)) {}

    void OnSetRemoteDescriptionComplete(webrtc::RTCError error) override { _onComplete(std::move(error)); }

  private:
    std::function<void(webrtc::RTCError)> _onComplete;
  };

} // namespace python_webrtc
