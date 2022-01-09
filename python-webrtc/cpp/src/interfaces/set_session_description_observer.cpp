//
// Created by Il'ya Semyonov on 1/6/22.
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
