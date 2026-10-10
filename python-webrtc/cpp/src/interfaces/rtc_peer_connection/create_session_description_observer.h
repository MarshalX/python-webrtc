//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_CREATE_SESSION_DESCRIPTION_OBSERVER_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_CREATE_SESSION_DESCRIPTION_OBSERVER_H_

#include <functional>
#include <memory>
#include <utility>

#include "../../utils/mailbox.h"
#include "rtc_peer_connection.h"

namespace webrtc {
  class RTCError;
}

namespace python_webrtc {

  // hands the description to `created` for the implicit answer of setLocalDescription
  class CreateSessionDescriptionObserver : public webrtc::CreateSessionDescriptionObserver {
  public:
    CreateSessionDescriptionObserver(std::weak_ptr<RTCPeerConnection> peerConnection,
                                     std::shared_ptr<Completion> completion,
                                     std::function<void(const RTCSessionDescription &)> created = nullptr)
        : _peerConnection(std::move(peerConnection)), _completion(std::move(completion)), _created(std::move(created)) {
    }

    void OnSuccess(webrtc::SessionDescriptionInterface *description) override;

    void OnFailure(webrtc::RTCError error) override;

  private:
    // the connection may be gone by the time the description is created
    std::weak_ptr<RTCPeerConnection> _peerConnection;
    std::shared_ptr<Completion> _completion;
    std::function<void(const RTCSessionDescription &)> _created;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_CREATE_SESSION_DESCRIPTION_OBSERVER_H_
