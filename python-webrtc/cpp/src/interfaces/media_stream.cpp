//
// Created by Il'ya Semyonov on 1/10/22.
//

#include "media_stream.h"

namespace python_webrtc {

  MediaStream::Impl::Impl(PeerConnectionFactory *factory)
      : _factory(factory ? factory : PeerConnectionFactory::GetOrCreateDefault()),
        _stream(_factory->factory()->CreateLocalMediaStream(rtc::CreateRandomUuid())),
        _shouldReleaseFactory(!factory) {}

  MediaStream::Impl::Impl(std::vector<MediaStreamTrack> &&tracks, PeerConnectionFactory *factory)
      : _factory(
      factory ? factory : tracks.empty() ? PeerConnectionFactory::GetOrCreateDefault() : tracks[0].factory()),
        _stream(_factory->factory()->CreateLocalMediaStream(rtc::CreateRandomUuid())),
        _shouldReleaseFactory(!factory && tracks.empty()) {
    for (auto &track: tracks) {
      if (track.track()->kind() == track.track()->kAudioKind) {
        auto audioTrack = static_cast<webrtc::AudioTrackInterface *>(track.track().get());
        _stream->AddTrack(audioTrack);
      } else {
        auto videoTrack = static_cast<webrtc::VideoTrackInterface *>(track.track().get());
        _stream->AddTrack(videoTrack);
      }
    }
  }

  MediaStream::Impl::Impl(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream, PeerConnectionFactory *factory)
      : _factory(factory ? factory : PeerConnectionFactory::GetOrCreateDefault()), _stream(std::move(stream)),
        _shouldReleaseFactory(!factory) {}

  MediaStream::Impl::~Impl() {
    if (_factory) {
      _factory = nullptr;
    }
    if (_shouldReleaseFactory) {
      PeerConnectionFactory::Release();
    }
  }

  std::vector<rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> MediaStream::tracks() {
    auto tracks = std::vector<rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>>();
    for (auto const &track: _impl._stream->GetAudioTracks()) {
      tracks.emplace_back(track);
    }
    for (auto const &track: _impl._stream->GetVideoTracks()) {
      tracks.emplace_back(track);
    }
    return tracks;
  }

  rtc::scoped_refptr<webrtc::MediaStreamInterface> MediaStream::stream() {
    return _impl._stream;
  }

  MediaStream::MediaStream() {
    // Local MediaStream
    _impl = MediaStream::Impl();
  }

  MediaStream::MediaStream(MediaStream *existedStream) {
    // Local MediaStream, existed MediaStream
    auto factory = existedStream->_impl._factory;
    auto tracks = std::vector<MediaStreamTrack>();

    for (auto const &track: existedStream->tracks()) {
      tracks.emplace_back(factory, track);
    }

    _impl = MediaStream::Impl(std::move(tracks), factory);
  }

  MediaStream::MediaStream(std::vector<MediaStreamTrack> tracks) {
    // Local MediaStream, Array of MediaStreamTrack
    _impl = MediaStream::Impl(std::move(tracks));
  }

  MediaStream::MediaStream(PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {
    // Remote MediaStream
    _impl = MediaStream::Impl(std::move(stream), factory);
  }

  void MediaStream::Init(pybind11::module &m) {
    pybind11::class_<MediaStream>(m, "MediaStream")
        .def_property_readonly("id", &MediaStream::GetId)
        .def_property_readonly("active", &MediaStream::GetActive)
        .def("getAudioTracks", &MediaStream::GetAudioTracks)
        .def("getVideoTracks", &MediaStream::GetVideoTracks)
        .def("getTracks", &MediaStream::GetTracks)
        .def("getTrackById", &MediaStream::GetTrackById)
        .def("addTrack", &MediaStream::AddTrack)
        .def("removeTrack", &MediaStream::RemoveTrack)
        .def("clone", &MediaStream::Clone);
  }

  std::string MediaStream::GetId() {
    return _impl._stream->id();
  }

  bool MediaStream::GetActive() {
    auto active = false;

    for (auto const &track: tracks()) {
      auto mediaStreamTrack = MediaStreamTrack(_impl._factory, track);
      active = active || mediaStreamTrack.active();
    }

    return active;
  }

  std::vector<MediaStreamTrack> MediaStream::GetAudioTracks() {
    auto tracks = std::vector<MediaStreamTrack>();

    for (auto const &track: _impl._stream->GetAudioTracks()) {
      tracks.emplace_back(_impl._factory, track);
    }

    return tracks;
  }

  std::vector<MediaStreamTrack> MediaStream::GetVideoTracks() {
    auto tracks = std::vector<MediaStreamTrack>();

    for (auto const &track: _impl._stream->GetVideoTracks()) {
      tracks.emplace_back(_impl._factory, track);
    }

    return tracks;
  }

  std::vector<MediaStreamTrack> MediaStream::GetTracks() {
    auto tracks = std::vector<MediaStreamTrack>();

    for (auto track: this->tracks()) {
      tracks.emplace_back(_impl._factory, std::move(track));
    }

    return tracks;
  }

  std::optional<MediaStreamTrack> MediaStream::GetTrackById(const std::string &label) {
    auto audioTrack = _impl._stream->FindAudioTrack(label);
    if (audioTrack) {
      return MediaStreamTrack(_impl._factory, audioTrack);
    }

    auto videoTrack = _impl._stream->FindVideoTrack(label);
    if (videoTrack) {
      return MediaStreamTrack(_impl._factory, videoTrack);
    }

    return {};
  }

  void MediaStream::AddTrack(MediaStreamTrack *mediaStreamTrack) {
    auto stream = _impl._stream;
    auto track = mediaStreamTrack->track();

    if (track->kind() == track->kAudioKind) {
      stream->AddTrack(static_cast<webrtc::AudioTrackInterface *>(track.get()));
    } else {
      stream->AddTrack(static_cast<webrtc::VideoTrackInterface *>(track.get()));
    }
  }

  void MediaStream::RemoveTrack(MediaStreamTrack *mediaStreamTrack) {
    auto stream = _impl._stream;
    auto track = mediaStreamTrack->track();

    if (track->kind() == track->kAudioKind) {
      stream->RemoveTrack(static_cast<webrtc::AudioTrackInterface *>(track.get()));
    } else {
      stream->RemoveTrack(static_cast<webrtc::VideoTrackInterface *>(track.get()));
    }
  }

  std::unique_ptr<MediaStream> MediaStream::Clone() {
    auto clonedStream = _impl._factory->factory()->CreateLocalMediaStream(rtc::CreateRandomUuid());

    for (auto const &track: this->tracks()) {
      if (track->kind() == track->kAudioKind) {
        auto audioTrack = static_cast<webrtc::AudioTrackInterface *>(track.get());
        auto source = audioTrack->GetSource();
        auto clonedTrack = _impl._factory->factory()->CreateAudioTrack(rtc::CreateRandomUuid(), source);
        clonedStream->AddTrack(clonedTrack);
      } else {
        auto videoTrack = static_cast<webrtc::VideoTrackInterface *>(track.get());
        auto source = videoTrack->GetSource();
        auto clonedTrack = _impl._factory->factory()->CreateVideoTrack(rtc::CreateRandomUuid(), source);
        clonedStream->AddTrack(clonedTrack);
      }
    }

    return std::make_unique<MediaStream>(_impl._factory, clonedStream);
  }

} // namespace python_webrtc
