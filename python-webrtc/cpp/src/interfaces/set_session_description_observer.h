//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_SET_SESSION_DESCRIPTION_OBSERVER_H_
#define PYTHON_WEBRTC_INTERFACES_SET_SESSION_DESCRIPTION_OBSERVER_H_

#include <functional>
#include <utility>

#include <api/rtc_error.h>
#include <api/set_local_description_observer_interface.h>
#include <api/set_remote_description_observer_interface.h>

namespace python_webrtc {

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

#endif // PYTHON_WEBRTC_INTERFACES_SET_SESSION_DESCRIPTION_OBSERVER_H_
