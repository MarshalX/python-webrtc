//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream.h"

#include <rtc_base/crypto_random.h>

#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  MediaStream::MediaStream(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream)
      : _factory(std::move(factory)), _stream(std::move(stream)) {
    for (const auto &track: tracks()) {
      _known.insert(track.get());
    }
    // see AliveGuard
    _factory->_signalingThread->PostTask(_alive.Guard([this]() { _stream->RegisterObserver(this); }));
  }

  MediaStream::~MediaStream() {
    BlockingDestructor release("MediaStream");
    _factory->_signalingThread->BlockingCall([this]() { _stream->UnregisterObserver(this); });
    DropListeners();
  }

  void MediaStream::OnChanged() {
    std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> added, removed;
    {
      std::lock_guard<std::mutex> lock(_tracksMutex);
      std::set<webrtc::MediaStreamTrackInterface *> current;
      for (const auto &track: tracks()) {
        current.insert(track.get());
        if (!_known.count(track.get())) {
          added.push_back(track);
        }
      }
      for (auto track: _known) {
        if (!current.count(track)) {
          removed.push_back(webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>(track));
        }
      }
      _known = std::move(current);
    }
    for (const auto &track: removed) {
      Emit("removetrack", MediaStreamTrack::holder().GetOrCreate(_factory, track));
    }
    for (const auto &track: added) {
      Emit("addtrack", MediaStreamTrack::holder().GetOrCreate(_factory, track));
    }
  }

  std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> MediaStream::tracks() {
    auto tracks = std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>>();
    for (auto const &track: _stream->GetAudioTracks()) {
      tracks.emplace_back(track);
    }
    for (auto const &track: _stream->GetVideoTracks()) {
      tracks.emplace_back(track);
    }
    return tracks;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::SyncTracks() {
    auto tracks = std::vector<std::shared_ptr<MediaStreamTrack>>();
    decltype(_tracks) current;
    // read before locking: they're calls to the signaling thread, where OnChanged takes the lock
    auto streamTracks = this->tracks();
    {
      std::lock_guard<std::mutex> lock(_tracksMutex);
      for (auto const &track: streamTracks) {
        auto it = _tracks.find(track.get());
        auto wrapper = it != _tracks.end() ? it->second : MediaStreamTrack::holder().GetOrCreate(_factory, track);
        current[track.get()] = wrapper;
        tracks.push_back(std::move(wrapper));
      }
      std::swap(_tracks, current);
    }
    // wrappers of removed tracks are released here, out of the lock
    return tracks;
  }

  std::shared_ptr<MediaStreamTrack> MediaStream::WrapTrack(
      webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track) {
    std::lock_guard<std::mutex> lock(_tracksMutex);
    auto it = _tracks.find(track.get());
    if (it != _tracks.end()) {
      return it->second;
    }

    auto wrapper = MediaStreamTrack::holder().GetOrCreate(_factory, track);
    _tracks[track.get()] = wrapper;
    return wrapper;
  }

  webrtc::scoped_refptr<webrtc::MediaStreamInterface> MediaStream::stream() {
    return _stream;
  }

  void MediaStream::Init(pybind11::module &m) {
    Listeners::BindClass<MediaStream>(m, "MediaStream")
        .def_property_readonly("id", nogil_fn(&MediaStream::GetId))
        .def_property_readonly("active", nogil_fn(&MediaStream::GetActive))
        .def("getAudioTracks", &MediaStream::GetAudioTracks, nogil())
        .def("getVideoTracks", &MediaStream::GetVideoTracks, nogil())
        .def("getTracks", &MediaStream::GetTracks, nogil())
        .def("getTrackById", &MediaStream::GetTrackById, nogil(), pybind11::arg("id"))
        .def("addTrack", &MediaStream::AddTrack, nogil(), pybind11::arg("track"))
        .def("removeTrack", &MediaStream::RemoveTrack, nogil(), pybind11::arg("track"))
        .def("clone", &MediaStream::Clone, nogil())
        .def_static("create", &MediaStream::Create, nogil(), pybind11::arg("tracks"));
  }

  std::string MediaStream::GetId() {
    return _stream->id();
  }

  bool MediaStream::GetActive() {
    auto active = false;

    for (auto const &track: SyncTracks()) {
      active = active || track->active();
    }

    return active;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::GetAudioTracks() {
    auto tracks = std::vector<std::shared_ptr<MediaStreamTrack>>();

    for (auto const &track: SyncTracks()) {
      if (track->track()->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
        tracks.push_back(track);
      }
    }

    return tracks;
  }

  std::vector<std::shared_ptr<MediaStreamTrack>> MediaStream::GetVideoTracks() {
    auto tracks = std::vector<std::shared_ptr<MediaStreamTrack>>();

    for (auto const &track: SyncTracks()) {
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
    for (const auto &track: GetTracks()) {
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
      std::lock_guard<std::mutex> lock(_tracksMutex);
      _known.insert(track.get());
    }

    if (track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      _stream->AddTrack(static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(*mediaStreamTrack));
    } else {
      _stream->AddTrack(static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(*mediaStreamTrack));
    }

    std::lock_guard<std::mutex> lock(_tracksMutex);
    _tracks[track.get()] = mediaStreamTrack;
  }

  void MediaStream::RemoveTrack(MediaStreamTrack &mediaStreamTrack) {
    auto track = mediaStreamTrack.track();
    {
      // changes made by Python fire no events
      std::lock_guard<std::mutex> lock(_tracksMutex);
      _known.erase(track.get());
    }

    if (track->kind() == webrtc::MediaStreamTrackInterface::kAudioKind) {
      _stream->RemoveTrack(static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(mediaStreamTrack));
    } else {
      _stream->RemoveTrack(static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(mediaStreamTrack));
    }

    std::shared_ptr<MediaStreamTrack> removed;
    {
      std::lock_guard<std::mutex> lock(_tracksMutex);
      auto it = _tracks.find(track.get());
      if (it != _tracks.end()) {
        removed = std::move(it->second);
        _tracks.erase(it);
      }
    }
  }

  std::shared_ptr<MediaStream> MediaStream::Clone() {
    auto clonedStream = _factory->factory()->CreateLocalMediaStream(webrtc::CreateRandomUuid());

    for (auto const &track: this->tracks()) {
      if (track->kind() == track->kAudioKind) {
        auto audioTrack = dynamic_cast<webrtc::AudioTrackInterface *>(track.get());
        auto source = audioTrack->GetSource();
        auto clonedTrack = _factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), source);
        clonedStream->AddTrack(clonedTrack);
      } else {
        auto videoTrack = dynamic_cast<webrtc::VideoTrackInterface *>(track.get());
        auto source = videoTrack->GetSource();
        auto clonedTrack = _factory->factory()->CreateVideoTrack(webrtc::scoped_refptr<webrtc::VideoTrackSourceInterface>(source), webrtc::CreateRandomUuid());
        clonedStream->AddTrack(clonedTrack);
      }
    }

    return MediaStream::holder().GetOrCreate(_factory, clonedStream);
  }

  std::shared_ptr<MediaStream> MediaStream::Create(const std::vector<std::shared_ptr<MediaStreamTrack>> &tracks) {
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = MediaStream::holder().GetOrCreate(
        factory, factory->factory()->CreateLocalMediaStream(webrtc::CreateRandomUuid()));
    for (const auto &track: tracks) {
      stream->AddTrack(track);
    }
    return stream;
  }

  InstanceHolder<MediaStream, webrtc::MediaStreamInterface> &MediaStream::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<MediaStream, webrtc::MediaStreamInterface>();
    return *holder;
  }

} // namespace python_webrtc
