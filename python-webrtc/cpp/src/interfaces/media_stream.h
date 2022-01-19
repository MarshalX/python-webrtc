//
// Created by Il'ya Semyonov on 1/10/22.
//

#pragma once

#include <webrtc/api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"

namespace webrtc {
  class MediaStreamInterface;

  class MediaStreamTrackInterface;
}

namespace python_webrtc {

// TODO class RTCMediaStreamInit;

  class MediaStream {
  public:
    explicit MediaStream();

//    TODO
//    MediaStream(RTCMediaStreamInit*);

    explicit MediaStream(MediaStream *);

    explicit MediaStream(std::vector<MediaStreamTrack>);

    MediaStream(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::MediaStreamInterface>);

    void static Init(pybind11::module &m);

    rtc::scoped_refptr<webrtc::MediaStreamInterface> stream();

    std::string GetId();

    bool GetActive();

    std::vector<MediaStreamTrack> GetAudioTracks();

    std::vector<MediaStreamTrack> GetVideoTracks();

    std::vector<MediaStreamTrack> GetTracks();

    std::optional<MediaStreamTrack> GetTrackById(const std::string &);

    void AddTrack(MediaStreamTrack *);

    void RemoveTrack(MediaStreamTrack *);

    std::unique_ptr<MediaStream> Clone();

  private:
    class Impl {
    public:
      Impl &operator=(Impl &&other) noexcept {
        if (&other != this) {
          _factory = other._factory;
          other._factory = nullptr;
          _stream = std::move(other._stream);
          _shouldReleaseFactory = other._shouldReleaseFactory;
          if (_shouldReleaseFactory) {
            other._shouldReleaseFactory = false;
          }
        }
        return *this;
      }

      explicit Impl(PeerConnectionFactory *factory = nullptr);

      Impl(std::vector<MediaStreamTrack> &&tracks, PeerConnectionFactory *factory = nullptr);

      Impl(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream, PeerConnectionFactory *factory = nullptr);

//      TODO
//      Impl(const RTCMediaStreamInit& init, PeerConnectionFactory* factory = nullptr);

      ~Impl();

      PeerConnectionFactory *_factory;
      rtc::scoped_refptr<webrtc::MediaStreamInterface> _stream;
      bool _shouldReleaseFactory;
    };

    std::vector<rtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> tracks();

    Impl _impl;
  };

} // namespace python_webrtc
