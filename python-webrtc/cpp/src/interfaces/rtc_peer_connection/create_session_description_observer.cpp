//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "create_session_description_observer.h"

#include <memory>

namespace python_webrtc {

  void CreateSessionDescriptionObserver::OnSuccess(webrtc::SessionDescriptionInterface *description) {
    const std::unique_ptr<webrtc::SessionDescriptionInterface> owned(description);
    if (auto peerConnection = _peerConnection.lock()) {
      peerConnection->SaveCreatedDescription(RTCSessionDescriptionInit::Wrap(owned.get()));
      RTCPeerConnection::ReleaseElsewhere(std::move(peerConnection));
    }
    _onSuccess(RTCSessionDescription::Wrap(owned.get()));
  }

  void CreateSessionDescriptionObserver::OnFailure(webrtc::RTCError error) {
    _onFailure(RTCCallbackException(std::move(error)));
  }

} // namespace python_webrtc
