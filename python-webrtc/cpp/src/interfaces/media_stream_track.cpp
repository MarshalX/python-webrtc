//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream_track.h"
#include "../utils/gil.h"

#include <rtc_base/crypto_random.h>

namespace python_webrtc {

  MediaStreamTrack::MediaStreamTrack(std::shared_ptr<PeerConnectionFactory> factory,
                                     webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track)
      : _factory(std::move(factory)), _track(std::move(track)) {
    _factory->_signalingThread->BlockingCall([this]() {
      _track->RegisterObserver(this);
      _observing = true;
    });
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
  }

  void MediaStreamTrack::Init(pybind11::module &m) {
    pybind11::class_<MediaStreamTrack, std::shared_ptr<MediaStreamTrack>>(m, "MediaStreamTrack")
        .def_property("enabled", nogil_fn(&MediaStreamTrack::GetEnabled), nogil_fn(&MediaStreamTrack::SetEnabled))
        .def_property_readonly("id", nogil_fn(&MediaStreamTrack::GetId))
        .def_property_readonly("kind", nogil_fn(&MediaStreamTrack::GetKind))
        .def_property_readonly("readyState", nogil_fn(&MediaStreamTrack::GetReadyState))
        .def_property_readonly("muted", nogil_fn(&MediaStreamTrack::GetMuted))
        .def("clone", &MediaStreamTrack::Clone, nogil())
        .def("stop", &MediaStreamTrack::Stop, nogil());
  }

  void MediaStreamTrack::Stop() {
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
    if (_track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded) {
      StopOnSignalingThread();
    }
  }

  void MediaStreamTrack::OnPeerConnectionClosed() {
    Stop();
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
    return _track->id();
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
    auto state = _ended
                 ? webrtc::MediaStreamTrackInterface::TrackState::kEnded
                 : _track->state();
    return state;
  }

  bool MediaStreamTrack::GetMuted() {
    return false;
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
