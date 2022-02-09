//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
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

    explicit MediaStream(std::vector<MediaStreamTrack *>);

    MediaStream(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::MediaStreamInterface>);

    static MediaStream *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::MediaStreamInterface>);

    void static Init(pybind11::module &m);

    static InstanceHolder<
        MediaStream *, rtc::scoped_refptr<webrtc::MediaStreamInterface>, PeerConnectionFactory *
    > *holder();

    rtc::scoped_refptr<webrtc::MediaStreamInterface> stream();

    std::string GetId();

    bool GetActive();

    // stl containers will be returned to python as a copy
    std::vector<MediaStreamTrack *> GetAudioTracks();

    std::vector<MediaStreamTrack *> GetVideoTracks();

    std::vector<MediaStreamTrack *> GetTracks();

    // it will be copied to python too
    std::optional<MediaStreamTrack *> GetTrackById(const std::string &);

    void AddTrack(MediaStreamTrack &);

    void RemoveTrack(MediaStreamTrack &);

    // must be returned to python as reference
    MediaStream *Clone();

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

      Impl(std::vector<MediaStreamTrack *> &&tracks, PeerConnectionFactory *factory = nullptr);

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
