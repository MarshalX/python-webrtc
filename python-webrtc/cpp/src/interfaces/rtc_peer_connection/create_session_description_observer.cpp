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
    auto peerConnection = _peerConnection.lock();
    if (peerConnection) {
      peerConnection->PrepareCreatedDescription(*owned);
    }
    auto created = RTCSessionDescription::Wrap(owned.get());
    if (peerConnection) {
      peerConnection->SaveCreatedDescription(created.init());
    }
    if (_created) {
      _created(created);
    } else {
      _completion->Succeed(created);
    }
  }

  void CreateSessionDescriptionObserver::OnFailure(webrtc::RTCError error) {
    _completion->Fail(RTCCallbackException(std::move(error)));
  }

} // namespace python_webrtc
