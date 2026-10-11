//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream.h"

#include <rtc_base/crypto_random.h>

#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  MediaStream::MediaStream(std::shared_ptr<PeerConnectionFactory> factory,
                           webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream)
      : _factory(std::move(factory)), _stream(std::move(stream)) {
    for (const auto &track : tracks()) {
      _known.insert(track.get());
    }
    _factory->signalingThread()->PostTask(Guard([this]() { _stream->RegisterObserver(this); }));
  }

  MediaStream::~MediaStream() {
    BlockingCallOn(_factory->signalingThread(), [this]() { _stream->UnregisterObserver(this); });
  }

  void MediaStream::OnChanged() {
    std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> added;
    std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> removed;
    {
      const std::scoped_lock lock(_tracksMutex);
      std::set<webrtc::MediaStreamTrackInterface *> current;
      for (const auto &track : tracks()) {
        current.insert(track.get());
        if (!_known.contains(track.get())) {
          added.push_back(track);
        }
      }
      for (auto *track : _known) {
        if (!current.contains(track)) {
          removed.emplace_back(track);
        }
      }
      _known = std::move(current);
    }
    for (const auto &track : removed) {
      Emit("removetrack", MediaStreamTrack::registry().GetOrCreate(_factory, track));
    }
    for (const auto &track : added) {
      Emit("addtrack", MediaStreamTrack::registry().GetOrCreate(_factory, track));
    }
  }

  std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> MediaStream::tracks() {
    auto tracks = std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>>();
    for (const auto &track : _stream->GetAudioTracks()) {
      tracks.emplace_back(track);
    }
    for (const auto &track : _stream->GetVideoTracks()) {
      tracks.emplace_back(track);
    }
    return tracks;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::SyncTracks() {
    std::vector<std::shared_ptr<MediaStreamTrack>> tracks;
    for (const auto &track : this->tracks()) {
      tracks.push_back(MediaStreamTrack::registry().GetOrCreate(_factory, track));
    }
    return tracks;
  }

  webrtc::scoped_refptr<webrtc::MediaStreamInterface> MediaStream::stream() {
    return _stream;
  }

  void MediaStream::Init(pybind11::module &m) {
    DefineBinding(pybind11::class_<MediaStream, Binding, std::shared_ptr<MediaStream>>(m, "MediaStream"))
        .def_property_readonly("_id", &MediaStream::Id)
        .def_property_readonly("id", nogil_fn(&MediaStream::GetId))
        .def_property_readonly("active", nogil_fn(&MediaStream::GetActive))
        .def("getAudioTracks", &MediaStream::GetAudioTracks, nogil())
        .def("getVideoTracks", &MediaStream::GetVideoTracks, nogil())
        .def("getTracks", &MediaStream::GetTracks, nogil())
        .def("getTrackById", &MediaStream::GetTrackById, nogil(), pybind11::arg("id"))
        .def("addTrack", &MediaStream::AddTrack, nogil(), pybind11::arg("track"))
        .def("removeTrack", &MediaStream::RemoveTrack, nogil(), pybind11::arg("track"))
        .def_static("create", &MediaStream::Create, nogil(), pybind11::arg("tracks"));
  }

  std::string MediaStream::GetId() {
    return _stream->id();
  }

  bool MediaStream::GetActive() {
    auto active = false;

    for (const auto &track : SyncTracks()) {
      active = active || track->active();
    }

    return active;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::GetAudioTracks() {
    auto tracks = std::vector<std::shared_ptr<MediaStreamTrack>>();

    for (const auto &track : SyncTracks()) {
      if (track->track()->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
        tracks.push_back(track);
      }
    }

    return tracks;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::GetVideoTracks() {
    auto tracks = std::vector<std::shared_ptr<MediaStreamTrack>>();

    for (const auto &track : SyncTracks()) {
      if (track->track()->kind() == webrtc::MediaStreamTrackInterface::kVideoKind) {
        tracks.push_back(track);
      }
    }

    return tracks;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::GetTracks() {
    return SyncTracks();
  }

  std::optional<std::shared_ptr<MediaStreamTrack>> MediaStream::GetTrackById(const std::string &id) {
    // by the id Python sees, which differs from the libwebrtc one for remote tracks
    for (const auto &track : GetTracks()) {
      if (track->GetId() == id) {
        return track;
      }
    }
    return {};
  }

  void MediaStream::AddTrack(const std::shared_ptr<MediaStreamTrack> &mediaStreamTrack) {
    auto track = mediaStreamTrack->track();
    {
      // changes made by Python fire no events
      const std::scoped_lock lock(_tracksMutex);
      _known.insert(track.get());
    }

    if (track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      _stream->AddTrack(static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(*mediaStreamTrack));
    } else {
      _stream->AddTrack(static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(*mediaStreamTrack));
    }
  }

  void MediaStream::RemoveTrack(MediaStreamTrack &mediaStreamTrack) {
    auto track = mediaStreamTrack.track();
    {
      // changes made by Python fire no events
      const std::scoped_lock lock(_tracksMutex);
      _known.erase(track.get());
    }

    if (track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      _stream->RemoveTrack(static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(mediaStreamTrack));
    } else {
      _stream->RemoveTrack(static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(mediaStreamTrack));
    }
  }

  std::shared_ptr<MediaStream> MediaStream::Create(const std::vector<std::shared_ptr<MediaStreamTrack>> &tracks) {
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = MediaStream::registry().GetOrCreate(
        factory, factory->factory()->CreateLocalMediaStream(webrtc::CreateRandomUuid()));
    for (const auto &track : tracks) {
      stream->AddTrack(track);
    }
    return stream;
  }

  Registry<MediaStream, webrtc::MediaStreamInterface> &MediaStream::registry() {
    static ForkLocal<Registry<MediaStream, webrtc::MediaStreamInterface>> registry;
    return registry.Get();
  }

} // namespace python_webrtc
