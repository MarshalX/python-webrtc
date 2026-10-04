//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream_track.h"

#include <cmath>
#include <rtc_base/crypto_random.h>

#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"
#include "rtc_video_track_source.h"

namespace python_webrtc {

  MediaStreamTrack::MediaStreamTrack(std::shared_ptr<PeerConnectionFactory> factory,
                                     webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track)
      : _factory(std::move(factory)), _track(std::move(track)),
        _source(SourceControl::Find(_track.get(), _track->id())) {
    // see AliveGuard
    _factory->signalingThread()->PostTask(_alive.Guard([this]() {
      _track->RegisterObserver(this);
      _observing = true;
      AttachMonitor();
    }));
  }

  MediaStreamTrack::~MediaStreamTrack() {
    const BlockingDestructor release("MediaStreamTrack");

    // after this the track can't notify us anymore: it notifies on the same thread
    _factory->signalingThread()->BlockingCall([this]() {
      DetachMonitor();
      if (_observing) {
        _track->UnregisterObserver(this);
        _observing = false;
      }
    });

    _track = nullptr;
    // released as the listeners are (see DropListeners)
    ReleasePythonObject(_constraints);
    DropListeners();
  }

  void MediaStreamTrack::AttachMonitor() {
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
      static_cast<webrtc::VideoTrackInterface *>(_track.get())->AddOrUpdateSink(&_monitor, webrtc::VideoSinkWants());
    } else {
      static_cast<webrtc::AudioTrackInterface *>(_track.get())->AddSink(&_monitor);
    }
    _monitoring = true;
  }

  void MediaStreamTrack::DetachMonitor() {
    if (!_monitoring) {
      return;
    }
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
      static_cast<webrtc::VideoTrackInterface *>(_track.get())->RemoveSink(&_monitor);
    } else {
      static_cast<webrtc::AudioTrackInterface *>(_track.get())->RemoveSink(&_monitor);
    }
    _monitoring = false;
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
        .def("_surfaceEnded", &MediaStreamTrack::SurfaceEnded, nogil())
        .def("_setLabel", &MediaStreamTrack::SetLabel, nogil(), pybind11::arg("label"))
        .def("_settings", &MediaStreamTrack::GetSettings)
        .def("_camera", &MediaStreamTrack::GetCamera, nogil())
        .def("_reconfigureCamera", &MediaStreamTrack::ReconfigureCamera, nogil(), pybind11::arg("width"),
             pybind11::arg("height"), pybind11::arg("frameRate"))
        .def_property("_constraints", &MediaStreamTrack::GetConstraints, &MediaStreamTrack::SetConstraints)
        .def_property("contentHint", nogil_fn(&MediaStreamTrack::GetContentHint),
                      nogil_fn(&MediaStreamTrack::SetContentHint));
  }

  void MediaStreamTrack::Stop() {
    _stopped = true;
    _surfacedEnded.Reset();
    _factory->signalingThread()->BlockingCall([this]() { StopOnSignalingThread(); });
    CloseListeners();
  }

  void MediaStreamTrack::StopOnSignalingThread() {
    if (_observing) {
      _track->UnregisterObserver(this);
      _observing = false;
    }
    _enabled = _track->enabled();
    _ended = true;
    NotifyEnded();
  }

  void MediaStreamTrack::AddEndObserver(const std::shared_ptr<TrackEndObserver> &observer) {
    {
      const std::scoped_lock lock(_endObserversMutex);
      if (!_ended) {
        _endObservers.push_back(observer);
        return;
      }
    }
    observer->OnTrackEnded();
  }

  void MediaStreamTrack::NotifyEnded() {
    std::vector<std::weak_ptr<TrackEndObserver>> observers;
    {
      const std::scoped_lock lock(_endObserversMutex);
      observers.swap(_endObservers);
    }
    for (auto &observer : observers) {
      if (auto locked = observer.lock()) {
        locked->OnTrackEnded();
      }
    }
  }

  void MediaStreamTrack::OnChanged() {
    if (_track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded && !_ended) {
      // ended by the remote peer or by renegotiation, rather than by stop()
      const bool emit = !_stopped;
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
    // a closed connection fires no events of its tracks, so their handlers go
    CloseListeners();
    _surfacedMuted.Reset();
    _surfacedEnded.Reset();
    Stop();
  }

  void MediaStreamTrack::MarkRemote() {
    _muted = true;
    {
      // a remote track has its own id, rather than the one in the description, which every receiver of it shares
      const std::scoped_lock lock(_idMutex);
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
    const bool previous = _muted.exchange(muted);
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
    CloseListeners();
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
    const std::scoped_lock lock(_idMutex);
    return _id ? *_id : _track->id();
  }

  std::string MediaStreamTrack::GetNativeId() {
    return _track->id();
  }

  std::string MediaStreamTrack::GetLabel() {
    const std::scoped_lock lock(_idMutex);
    return _label;
  }

  void MediaStreamTrack::SetLabel(const std::string &label) {
    const std::scoped_lock lock(_idMutex);
    _label = label;
  }

  webrtc::MediaType MediaStreamTrack::GetKind() {
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      return webrtc::MediaType::AUDIO;
    }
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
      return webrtc::MediaType::VIDEO;
    }

    return webrtc::MediaType::UNSUPPORTED;
  }

  webrtc::MediaStreamTrackInterface::TrackState MediaStreamTrack::GetReadyState() {
    const bool ended = _ended || _track->state() == webrtc::MediaStreamTrackInterface::TrackState::kEnded;
    // without listeners (outside of an event loop), no event is going to surface it
    const bool surfaced = HasListeners() ? _surfacedEnded.Get(ended) : ended;
    return surfaced ? webrtc::MediaStreamTrackInterface::TrackState::kEnded
                    : webrtc::MediaStreamTrackInterface::TrackState::kLive;
  }

  bool MediaStreamTrack::GetMuted() {
    return _surfacedMuted.Get(_muted);
  }

  pybind11::dict MediaStreamTrack::GetSettings() {
    std::optional<TrackMonitor::Video> video;
    std::optional<TrackMonitor::Audio> audio;
    std::optional<std::tuple<int, int, double>> camera;
    bool microphone = false;
    {
      const gil_release release;
      video = _monitor.video();
      audio = _monitor.audio();
      camera = GetCamera();
      if (_source) {
        const std::scoped_lock lock(_source->mutex);
        microphone = _source->microphone;
      }
    }
    pybind11::dict settings;
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
      if (camera) {
        auto [width, height, frameRate] = *camera;
        settings["width"] = width;
        settings["height"] = height;
        settings["frame_rate"] = frameRate;
        settings["device"] = "camera";
      }
      if (video) {
        // the frames themselves, rather than what the camera was asked for
        settings["width"] = video->width;
        settings["height"] = video->height;
        if (video->frameRate) {
          settings["frame_rate"] = *video->frameRate;
        }
      }
    } else {
      if (microphone) {
        settings["device"] = "microphone";
      }
      if (audio) {
        settings["sample_rate"] = audio->sampleRate;
        settings["channel_count"] = audio->channels;
        settings["sample_size"] = audio->bitsPerSample;
      }
    }
    return settings;
  }

  std::optional<std::tuple<int, int, double>> MediaStreamTrack::GetCamera() {
    if (!_source) {
      return std::nullopt;
    }
    const std::scoped_lock lock(_source->mutex);
    int width{};
    int height{};
    double frameRate = NAN;
    if ((_source->camera == nullptr) || !_source->camera->IsCamera(&width, &height, &frameRate)) {
      return std::nullopt;
    }
    return std::make_tuple(width, height, frameRate);
  }

  bool MediaStreamTrack::ReconfigureCamera(int width, int height, double frameRate) {
    if (!_source || _ended) {
      return false;
    }
    const std::scoped_lock lock(_source->mutex);
    if (_source->camera == nullptr) {
      return false;
    }
    _source->camera->StartCamera(width, height, frameRate);
    return true;
  }

  pybind11::object MediaStreamTrack::GetConstraints() {
    return _constraints ? _constraints : pybind11::none();
  }

  void MediaStreamTrack::SetConstraints(pybind11::object constraints) {
    _constraints = constraints.is_none() ? pybind11::object() : std::move(constraints);
  }

  std::string MediaStreamTrack::GetContentHint() {
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      const std::scoped_lock lock(_contentHintMutex);
      return _audioContentHint;
    }
    switch (static_cast<webrtc::VideoTrackInterface *>(_track.get())->content_hint()) {
    case webrtc::VideoTrackInterface::ContentHint::kFluid:
      return "motion";
    case webrtc::VideoTrackInterface::ContentHint::kDetailed:
      return "detail";
    case webrtc::VideoTrackInterface::ContentHint::kText:
      return "text";
    default:
      return "";
    }
  }

  void MediaStreamTrack::SetContentHint(const std::string &hint) {
    // hints of the other kind, and unknown ones, are ignored
    if (_track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      if (hint.empty() || hint == "speech" || hint == "speaking" || hint == "music") {
        const std::scoped_lock lock(_contentHintMutex);
        _audioContentHint = hint;
      }
      return;
    }
    using ContentHint = webrtc::VideoTrackInterface::ContentHint;
    auto *track = static_cast<webrtc::VideoTrackInterface *>(_track.get());
    if (hint.empty()) {
      track->set_content_hint(ContentHint::kNone);
    } else if (hint == "motion") {
      track->set_content_hint(ContentHint::kFluid);
    } else if (hint == "detail") {
      track->set_content_hint(ContentHint::kDetailed);
    } else if (hint == "text") {
      track->set_content_hint(ContentHint::kText);
    }
  }

  std::shared_ptr<MediaStreamTrack> MediaStreamTrack::Clone() {
    auto label = webrtc::CreateRandomUuid();
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> clonedTrack = nullptr;

    if (_track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      auto *audioTrack = dynamic_cast<webrtc::AudioTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateAudioTrack(label, audioTrack->GetSource());
    } else {
      auto *videoTrack = dynamic_cast<webrtc::VideoTrackInterface *>(_track.get());
      clonedTrack = _factory->factory()->CreateVideoTrack(
          webrtc::scoped_refptr<webrtc::VideoTrackSourceInterface>(videoTrack->GetSource()), label);
    }

    if (_source) {
      // the clone has the same device
      SourceControl::Register(clonedTrack.get(), clonedTrack->id(), _source);
    }
    auto clonedMediaStreamTrack = holder().GetOrCreate(_factory, clonedTrack);
    clonedMediaStreamTrack->SetLabel(GetLabel());
    if (_ended) {
      clonedMediaStreamTrack->Stop();
    }
    return clonedMediaStreamTrack;
  }

  MediaStreamTrack::operator webrtc::scoped_refptr<webrtc::AudioTrackInterface>() {
    return webrtc::scoped_refptr<webrtc::AudioTrackInterface>(
        dynamic_cast<webrtc::AudioTrackInterface *>(_track.get()));
  }

  MediaStreamTrack::operator webrtc::scoped_refptr<webrtc::VideoTrackInterface>() {
    return webrtc::scoped_refptr<webrtc::VideoTrackInterface>(
        dynamic_cast<webrtc::VideoTrackInterface *>(_track.get()));
  }

  InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface> &MediaStreamTrack::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto *holder = new InstanceHolder<MediaStreamTrack, webrtc::MediaStreamTrackInterface>();
    return *holder;
  }

} // namespace python_webrtc
