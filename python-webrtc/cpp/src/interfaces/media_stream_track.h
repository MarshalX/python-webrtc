//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"

namespace python_webrtc {

  class MediaStreamTrack : public webrtc::ObserverInterface {
  public:
    explicit MediaStreamTrack(
        std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>);

    ~MediaStreamTrack() override;

    void static Init(pybind11::module &m);

    static InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface> &holder();

    void Stop();

    // ObserverInterface
    void OnChanged() override;

    void OnPeerConnectionClosed();

    bool GetEnabled();

    void SetEnabled(bool);

    std::string GetId();

    webrtc::MediaType GetKind();

    webrtc::MediaStreamTrackInterface::TrackState GetReadyState();

    bool GetMuted();

    std::shared_ptr<MediaStreamTrack> Clone();

    bool active() { return !_ended && _track->state() == webrtc::MediaStreamTrackInterface::TrackState::kLive; }

    const std::shared_ptr<PeerConnectionFactory> &factory() { return _factory; }

    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track() { return _track; }

    explicit operator webrtc::scoped_refptr<webrtc::AudioTrackInterface>();

    explicit operator webrtc::scoped_refptr<webrtc::VideoTrackInterface>();

  private:
    // must be called on the signaling thread, where the track notifies its observers
    void StopOnSignalingThread();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> _track;

    // accessed on the signaling thread only
    bool _observing = false;

    std::atomic<bool> _ended = false;
    std::atomic<bool> _enabled = false;
  };

} // namespace python_webrtc
