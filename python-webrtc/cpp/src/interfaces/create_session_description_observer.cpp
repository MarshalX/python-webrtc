//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "create_session_description_observer.h"

namespace python_webrtc {

  void CreateSessionDescriptionObserver::OnSuccess(webrtc::SessionDescriptionInterface *description) {
    // TODO
    // ref: https://developer.mozilla.org/en-US/docs/Web/API/RTCSessionDescription/RTCSessionDescription
    // Note: This is no longer necessary, however; RTCPeerConnection.setLocalDescription()
    // and other methods which take SDP as input now directly accept an object conforming to the
    // RTCSessionDescriptionInit dictionary, so you don't have to instantiate an RTCSessionDescription yourself.

    _peerConnection->SaveLastSdp(RTCSessionDescriptionInit::Wrap(description));
    _onSuccess(RTCSessionDescription::Wrap(description));
    delete description;
  }

  void CreateSessionDescriptionObserver::OnFailure(webrtc::RTCError error) {
    _onFailure(wrapRTCErrorForCallback(error));
  }

}
