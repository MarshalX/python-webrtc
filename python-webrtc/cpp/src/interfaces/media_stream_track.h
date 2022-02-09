//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"

namespace python_webrtc {

  class MediaStreamTrack : public webrtc::ObserverInterface {
  public:
    explicit MediaStreamTrack(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>);

    static MediaStreamTrack *Create(
        PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track);

    ~MediaStreamTrack() override;

    void static Init(pybind11::module &m);

    static InstanceHolder<
        MediaStreamTrack *, rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>, PeerConnectionFactory *
    > *holder();

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

    // should be returned to python as reference! because we holding it in our holder
    MediaStreamTrack *Clone();

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
