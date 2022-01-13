//
// Created by Il'ya Semyonov on 1/10/22.
//

#pragma once

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"

namespace python_webrtc {

  class MediaStreamTrack : public webrtc::ObserverInterface {
  public:
    explicit MediaStreamTrack(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>);

    ~MediaStreamTrack() override;

    void static Init(pybind11::module &m);

    void Stop();

    // ObserverInterface
    void OnChanged() override;

    void OnPeerConnectionClosed();

    bool GetEnabled();

    void SetEnabled(bool);

    std::string GetId();

    std::string GetKind();

    webrtc::MediaStreamTrackInterface::TrackState GetReadyState();

    bool GetMuted();

    std::unique_ptr<MediaStreamTrack> Clone();

    bool active() { return !_ended && _track->state() == webrtc::MediaStreamTrackInterface::TrackState::kLive; }

    PeerConnectionFactory *factory() { return _factory; }

    rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track() { return _track; }

    explicit operator rtc::scoped_refptr<webrtc::AudioTrackInterface>();

    explicit operator rtc::scoped_refptr<webrtc::VideoTrackInterface>();

  private:
    bool _ended = false;
    bool _enabled;
    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> _track;
  };

} // namespace python_webrtc
