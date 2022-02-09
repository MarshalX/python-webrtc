//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "set_session_description_observer.h"

namespace python_webrtc {

  void SetSessionDescriptionObserver::OnSuccess() {
    _on_success();
  }

  void SetSessionDescriptionObserver::OnFailure(webrtc::RTCError) {
//      TODO call onFail
  }

} // namespace python_webrtc
