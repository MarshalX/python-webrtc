//
// Created by Il'ya Semyonov on 1/10/22.
//

#include "media_stream_track.h"

#include <rtc_base/helpers.h>

namespace python_webrtc {

  MediaStreamTrack::MediaStreamTrack(PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track) {
    _factory = factory;

    _track = std::move(track);
    _track->RegisterObserver(this);

//    TODO mb remove
    _enabled = false;
  }

  MediaStreamTrack::~MediaStreamTrack() {
    _track = nullptr;
    _factory = nullptr;
  }

  void MediaStreamTrack::Init(pybind11::module &m) {
    pybind11::class_<MediaStreamTrack>(m, "MediaStreamTrack")
        .def_property("enabled", &MediaStreamTrack::GetEnabled, &MediaStreamTrack::SetEnabled)
        .def_property_readonly("id", &MediaStreamTrack::GetId)
        .def_property_readonly("kind", &MediaStreamTrack::GetKind)
        .def_property_readonly("readyState", &MediaStreamTrack::GetReadyState)
        .def_property_readonly("muted", &MediaStreamTrack::GetMuted)
        .def("clone", &MediaStreamTrack::Clone)
        .def("stop", &MediaStreamTrack::Stop);
  }

  void MediaStreamTrack::Stop() {
    _track->UnregisterObserver(this);
    _ended = true;
    _enabled = _track->enabled();
  }

  void MediaStreamTrack::OnChanged() {
    if (_track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded) {
      Stop();
    }
  }

  void MediaStreamTrack::OnPeerConnectionClosed() {
    Stop();
  }

  bool MediaStreamTrack::GetEnabled() {
    return _ended ? _enabled : _track->enabled();
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

  std::string MediaStreamTrack::GetKind() {
    return _track->kind();
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

  std::unique_ptr<MediaStreamTrack> MediaStreamTrack::Clone() {
    auto label = rtc::CreateRandomUuid();
    rtc::scoped_refptr<webrtc::MediaStreamTrackInterface> clonedTrack = nullptr;

    if (_track->kind() == _track->kAudioKind) {
      auto audioTrack = static_cast<webrtc::AudioTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateAudioTrack(label, audioTrack->GetSource());
    } else {
      auto videoTrack = static_cast<webrtc::VideoTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateVideoTrack(label, videoTrack->GetSource());
    }

    auto clonedMediaStreamTrack = std::make_unique<MediaStreamTrack>(_factory, clonedTrack);
    if (_ended) {
      clonedMediaStreamTrack->Stop();
    }
    return clonedMediaStreamTrack;
  }

  MediaStreamTrack::operator rtc::scoped_refptr<webrtc::AudioTrackInterface>() {
    return {static_cast<webrtc::AudioTrackInterface *>(_track.get())};
  }

  MediaStreamTrack::operator rtc::scoped_refptr<webrtc::VideoTrackInterface>() {
    return {static_cast<webrtc::VideoTrackInterface *>(_track.get())};
  }

} // namespace python_webrtc
