//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_TRACK_H_
#define PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_TRACK_H_

#include <atomic>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../enums/enums.h"
#include "../media/source_control.h"
#include "../media/track_monitor.h"
#include "../utils/alive_guard.h"
#include "../utils/held_events.h"
#include "../utils/instance_holder.h"
#include "../utils/listeners.h"
#include "../utils/surfaced.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // Told once when a track ends, by stop() or otherwise
  class TrackEndObserver {
  public:
    virtual ~TrackEndObserver() = default;

    virtual void OnTrackEnded() = 0;
  };

  class MediaStreamTrack : public webrtc::ObserverInterface, public Listeners {
  public:
    explicit MediaStreamTrack(std::shared_ptr<PeerConnectionFactory> factory,
                              webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track);

    ~MediaStreamTrack() override;

    MediaStreamTrack(const MediaStreamTrack &) = delete;
    MediaStreamTrack &operator=(const MediaStreamTrack &) = delete;

    static void Init(pybind11::module &m);

    static InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface> &holder();

    void Stop();

    // ObserverInterface
    void OnChanged() override;

    void OnPeerConnectionClosed();

    bool GetEnabled();

    void SetEnabled(bool enabled);

    std::string GetId();

    // the id of the libwebrtc track, which the stats refer to
    std::string GetNativeId();

    std::string GetLabel();

    void SetLabel(const std::string &label);

    webrtc::MediaType GetKind();

    webrtc::MediaStreamTrackInterface::TrackState GetReadyState();

    bool GetMuted();

    // A remote track is muted until media arrives
    void MarkRemote();

    void SetMuted(bool muted);

    // see Surfaced
    void SurfaceMuted(bool muted);

    void SurfaceEnded();

    // Keeps the ended event until ReleaseEnded(): an operation that ends the track (like setting a description)
    // resolves before it, while the other events of the track (like mute) aren't held
    void HoldEnded();

    void ReleaseEnded();

    std::shared_ptr<MediaStreamTrack> Clone();

    // what the track carries (width, height, frame_rate, sample_rate, channel_count, sample_size) and its device
    // ("camera", "microphone"), as far as they're known
    pybind11::dict GetSettings();

    // the size and frame rate of the synthetic camera of the track, if it has one
    std::optional<std::tuple<int, int, double>> GetCamera();

    // changes the size and frame rate of the synthetic camera of the track; false if it has none
    bool ReconfigureCamera(int width, int height, double frameRate);

    // the constraints applied last, kept by the track as its wrappers come and go
    pybind11::object GetConstraints();

    void SetConstraints(pybind11::object constraints);

    std::string GetContentHint();

    void SetContentHint(const std::string &hint);

    // told right away if the track has ended already
    void AddEndObserver(const std::shared_ptr<TrackEndObserver> &observer);

    bool ended() { return _ended; }

    bool active() { return !_ended && _track->state() == webrtc::MediaStreamTrackInterface::TrackState::kLive; }

    const std::shared_ptr<PeerConnectionFactory> &factory() { return _factory; }

    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track() { return _track; }

    explicit operator webrtc::scoped_refptr<webrtc::AudioTrackInterface>();

    explicit operator webrtc::scoped_refptr<webrtc::VideoTrackInterface>();

  private:
    // must be called on the signaling thread, where the track notifies its observers
    void StopOnSignalingThread();

    void NotifyEnded();

    // the monitor sees what the track carries, for its settings; on the signaling thread
    void AttachMonitor();

    void DetachMonitor();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> _track;

    // accessed on the signaling thread only
    bool _observing = false;

    std::atomic<bool> _ended = false;
    std::atomic<bool> _enabled = false;
    std::atomic<bool> _muted = false;
    Surfaced<bool> _surfacedMuted;
    Surfaced<bool> _surfacedEnded;
    HeldEvents _heldEnded;

    std::mutex _idMutex;
    std::optional<std::string> _id;
    std::string _label;
    // stop() ends a track without an ended event
    std::atomic<bool> _stopped = false;

    std::shared_ptr<SourceControl> _source;
    TrackMonitor _monitor;
    // accessed on the signaling thread only
    bool _monitoring = false;
    pybind11::object _constraints;
    // audio tracks keep their hint: libwebrtc has none for them
    std::mutex _contentHintMutex;
    std::string _audioContentHint;

    std::mutex _endObserversMutex;
    std::vector<std::weak_ptr<TrackEndObserver>> _endObservers;

    // see AliveGuard
    AliveGuard _alive;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_TRACK_H_
