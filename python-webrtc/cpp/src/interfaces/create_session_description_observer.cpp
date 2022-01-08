//
// Created by Il'ya Semyonov on 1/6/22.
//

#include "create_session_description_observer.h"
#include "python-webrtc/cpp/src/models/python_webrtc/rtc_session_description.h"

python_webrtc::CreateSessionDescriptionObserver::CreateSessionDescriptionObserver(
    python_webrtc::RTCPeerConnection *peer_connection, std::function<void(RTCSessionDescription)> &on_success) {
  _on_success = on_success;
  _peer_connection = peer_connection;
}

void python_webrtc::CreateSessionDescriptionObserver::OnSuccess(webrtc::SessionDescriptionInterface *description) {
  // TODO
  // ref: https://developer.mozilla.org/en-US/docs/Web/API/RTCSessionDescription/RTCSessionDescription
  // Note: This is no longer necessary, however; RTCPeerConnection.setLocalDescription()
  // and other methods which take SDP as input now directly accept an object conforming to the
  // RTCSessionDescriptionInit dictionary, so you don't have to instantiate an RTCSessionDescription yourself.

  _peer_connection->SaveLastSdp(RTCSessionDescriptionInit::Wrap(description));
  _on_success(RTCSessionDescription::Wrap(description));
  delete description;
}

void python_webrtc::CreateSessionDescriptionObserver::OnFailure(webrtc::RTCError) {
//      TODO call onFail
}
