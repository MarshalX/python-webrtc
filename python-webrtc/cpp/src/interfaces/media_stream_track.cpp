//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream_track.h"

#include <rtc_base/crypto_random.h>

#include "../utils/gil.h"

namespace python_webrtc {

  MediaStreamTrack::MediaStreamTrack(std::shared_ptr<PeerConnectionFactory> factory,
                                     webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track)
      : _factory(std::move(factory)), _track(std::move(track)) {
    // see AliveGuard
    _factory->_signalingThread->PostTask(_alive.Guard([this]() {
      _track->RegisterObserver(this);
      _observing = true;
    }));
  }

  MediaStreamTrack::~MediaStreamTrack() {
    gil_release_if_held release;

    // after this the track can't notify us anymore: it notifies on the same thread
    _factory->_signalingThread->BlockingCall([this]() {
      if (_observing) {
        _track->UnregisterObserver(this);
        _observing = false;
      }
    });

    _track = nullptr;
    DropListeners();
  }

  void MediaStreamTrack::Init(pybind11::module &m) {
    Listeners::BindClass<MediaStreamTrack>(m, "MediaStreamTrack")
        .def_property("enabled", nogil_fn(&MediaStreamTrack::GetEnabled), nogil_fn(&MediaStreamTrack::SetEnabled))
        .def_property_readonly("id", nogil_fn(&MediaStreamTrack::GetId))
        .def_property_readonly("label", nogil_fn(&MediaStreamTrack::GetLabel))
        .def_property_readonly("kind", nogil_fn(&MediaStreamTrack::GetKind))
        .def_property_readonly("readyState", nogil_fn(&MediaStreamTrack::GetReadyState))
        .def_property_readonly("muted", nogil_fn(&MediaStreamTrack::GetMuted))
        .def("clone", &MediaStreamTrack::Clone, nogil())
        .def("stop", &MediaStreamTrack::Stop, nogil())
        .def_property_readonly("_nativeId", nogil_fn(&MediaStreamTrack::GetNativeId))
        .def("_surfaceMuted", &MediaStreamTrack::SurfaceMuted, nogil(), pybind11::arg("muted"))
        .def("_surfaceEnded", &MediaStreamTrack::SurfaceEnded, nogil());
  }

  void MediaStreamTrack::Stop() {
    _stopped = true;
    _surfacedEnded.Reset();
    _factory->_signalingThread->BlockingCall([this]() { StopOnSignalingThread(); });
  }

  void MediaStreamTrack::StopOnSignalingThread() {
    if (_observing) {
      _track->UnregisterObserver(this);
      _observing = false;
    }
    _enabled = _track->enabled();
    _ended = true;
  }

  void MediaStreamTrack::OnChanged() {
    if (_track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded && !_ended) {
      // ended by the remote peer or by renegotiation, rather than by stop()
      bool emit = !_stopped;
      if (emit) {
        // the track is live until its ended event (see Surfaced)
        _surfacedEnded.Changed(IsTracked(), false);
      }
      StopOnSignalingThread();
      if (emit) {
        _heldEnded.Emit([this]() { Emit("ended"); });
      }
    }
  }

  void MediaStreamTrack::OnPeerConnectionClosed() {
    // a closed connection fires no events of its tracks
    Mute();
    _surfacedMuted.Reset();
    _surfacedEnded.Reset();
    Stop();
  }

  void MediaStreamTrack::MarkRemote() {
    _muted = true;
    {
      // a remote track has its own id, rather than the one in the description, which every receiver of it shares
      std::lock_guard<std::mutex> lock(_idMutex);
      _id = webrtc::CreateRandomUuid();
      _label = _track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind ? "remote audio" : "remote video";
    }
    // its events (like ended) are kept until Python has the track
    Hold();
  }

  void MediaStreamTrack::SetMuted(bool muted) {
    if (_ended) {
      // an ended track stays as it was
      return;
    }
    bool previous = _muted.exchange(muted);
    if (previous != muted) {
      // a held remote track keeps showing the previous value until its event is delivered
      _surfacedMuted.Changed(IsTracked(), previous);
      Emit(muted ? "mute" : "unmute", muted);
    }
  }

  void MediaStreamTrack::SurfaceMuted(bool muted) {
    _surfacedMuted.Surface(muted);
  }

  void MediaStreamTrack::HoldEnded() {
    _heldEnded.Hold();
  }

  void MediaStreamTrack::ReleaseEnded() {
    _heldEnded.Release();
  }

  void MediaStreamTrack::SurfaceEnded() {
    _surfacedEnded.Reset();
  }

  bool MediaStreamTrack::GetEnabled() {
    return _ended ? _enabled.load() : _track->enabled();
  }

  void MediaStreamTrack::SetEnabled(bool enabled) {
    if (_ended) {
      _enabled = enabled;
    } else {
      _track->set_enabled(enabled);
    }
  }

  std::string MediaStreamTrack::GetId() {
    std::lock_guard<std::mutex> lock(_idMutex);
    return _id ? *_id : _track->id();
  }

  std::string MediaStreamTrack::GetNativeId() {
    return _track->id();
  }

  std::string MediaStreamTrack::GetLabel() {
    std::lock_guard<std::mutex> lock(_idMutex);
    return _label;
  }

  void MediaStreamTrack::SetLabel(const std::string &label) {
    std::lock_guard<std::mutex> lock(_idMutex);
    _label = label;
  }

  webrtc::MediaType MediaStreamTrack::GetKind() {
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      return webrtc::MediaType::AUDIO;
    } else if (_track->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
      return webrtc::MediaType::VIDEO;
    }

    return webrtc::MediaType::UNSUPPORTED;
  }

  webrtc::MediaStreamTrackInterface::TrackState MediaStreamTrack::GetReadyState() {
    bool ended = _ended || _track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded;
    // without listeners (outside of an event loop), no event is going to surface it
    return (HasListeners() ? _surfacedEnded.Get(ended) : ended)
           ? webrtc::MediaStreamTrackInterface::TrackState::kEnded
           : webrtc::MediaStreamTrackInterface::TrackState::kLive;
  }

  bool MediaStreamTrack::GetMuted() {
    return _surfacedMuted.Get(_muted);
  }

  std::shared_ptr<MediaStreamTrack> MediaStreamTrack::Clone() {
    auto label = webrtc::CreateRandomUuid();
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> clonedTrack = nullptr;

    if (_track->kind() == _track->kAudioKind) {
      auto audioTrack = dynamic_cast<webrtc::AudioTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateAudioTrack(label, audioTrack->GetSource());
    } else {
      auto videoTrack = dynamic_cast<webrtc::VideoTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateVideoTrack(webrtc::scoped_refptr<webrtc::VideoTrackSourceInterface>(videoTrack->GetSource()), label);
    }

    auto clonedMediaStreamTrack = holder().GetOrCreate(_factory, clonedTrack);
    clonedMediaStreamTrack->SetLabel(GetLabel());
    if (_ended) {
      clonedMediaStreamTrack->Stop();
    }
    return clonedMediaStreamTrack;
  }

  MediaStreamTrack::operator webrtc::scoped_refptr<webrtc::AudioTrackInterface>() {
    return webrtc::scoped_refptr<webrtc::AudioTrackInterface>(dynamic_cast<webrtc::AudioTrackInterface *>(_track.get()));
  }

  MediaStreamTrack::operator webrtc::scoped_refptr<webrtc::VideoTrackInterface>() {
    return webrtc::scoped_refptr<webrtc::VideoTrackInterface>(dynamic_cast<webrtc::VideoTrackInterface *>(_track.get()));
  }

  InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface> &MediaStreamTrack::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface>();
    return *holder;
  }

} // namespace python_webrtc
