//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "create_session_description_observer.h"

namespace python_webrtc {

  void CreateSessionDescriptionObserver::OnSuccess(webrtc::SessionDescriptionInterface *description) {
    if (auto peerConnection = _peerConnection.lock()) {
      peerConnection->SaveCreatedDescription(RTCSessionDescriptionInit::Wrap(description));
      RTCPeerConnection::ReleaseElsewhere(std::move(peerConnection));
    }
    _onSuccess(RTCSessionDescription::Wrap(description));
    delete description;
  }

  void CreateSessionDescriptionObserver::OnFailure(webrtc::RTCError error) {
    _onFailure(RTCCallbackException(std::move(error)));
  }

}
