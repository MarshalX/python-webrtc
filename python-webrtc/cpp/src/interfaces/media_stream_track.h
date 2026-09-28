//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../utils/alive_guard.h"
#include "../utils/listeners.h"

namespace python_webrtc {

  class MediaStreamTrack : public webrtc::ObserverInterface, public Listeners {
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

    std::string GetLabel();

    webrtc::MediaType GetKind();

    webrtc::MediaStreamTrackInterface::TrackState GetReadyState();

    bool GetMuted();

    // A remote track is muted until media arrives
    void MarkRemote();

    void SetMuted(bool muted);

    void SurfaceMuted(bool muted);

    void SurfaceEnded();

    // Keeps the ended event until ReleaseEnded(), as a description operation queues it after it completes,
    // while other events (like mute) come before
    void HoldEnded();

    void ReleaseEnded();

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
    std::atomic<bool> _muted = false;
    Surfaced<bool> _surfacedMuted;
    Surfaced<bool> _surfacedEnded;

    std::mutex _endedMutex;
    bool _holdingEnded = false;
    bool _endedHeld = false;

    std::mutex _idMutex;
    std::optional<std::string> _id;
    std::string _label;
    // stop() ends a track without an ended event
    std::atomic<bool> _stopped = false;

    // the observer registration posted by the constructor
    AliveGuard _alive;
  };

} // namespace python_webrtc
