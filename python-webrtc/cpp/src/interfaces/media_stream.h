//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>
#include <unordered_map>

#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "../utils/alive_guard.h"
#include "../utils/listeners.h"

#include <set>

namespace webrtc {

  class MediaStreamInterface;

  class MediaStreamTrackInterface;

}

namespace python_webrtc {

  // Emits addtrack and removetrack when libwebrtc changes the tracks of a remote stream
  class MediaStream : public webrtc::ObserverInterface, public Listeners {
  public:
    MediaStream(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::MediaStreamInterface>);

    ~MediaStream() override;

    // ObserverInterface, on the signaling thread
    void OnChanged() override;

    void static Init(pybind11::module &m);

    // A new stream of these tracks (new MediaStream() in a browser)
    static std::shared_ptr<MediaStream> Create(const std::vector<std::shared_ptr<MediaStreamTrack>> &tracks);

    static InstanceHolder<MediaStream, webrtc::MediaStreamInterface> &holder();

    webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream();

    std::string GetId();

    bool GetActive();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetAudioTracks();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetVideoTracks();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetTracks();

    std::optional<std::shared_ptr<MediaStreamTrack>> GetTrackById(const std::string &);

    void AddTrack(const std::shared_ptr<MediaStreamTrack> &);

    void RemoveTrack(MediaStreamTrack &);

    std::shared_ptr<MediaStream> Clone();

  private:
    std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> tracks();

    // wrappers of the current tracks of the stream; the stream owns them, so their state outlives Python references
    std::vector<std::shared_ptr<MediaStreamTrack>> SyncTracks();

    std::shared_ptr<MediaStreamTrack> WrapTrack(webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>);

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::MediaStreamInterface> _stream;

    std::mutex _tracksMutex;
    std::unordered_map<webrtc::MediaStreamTrackInterface *, std::shared_ptr<MediaStreamTrack>> _tracks;
    // the tracks the stream had when last notified, or as Python changed them, guarded by _tracksMutex
    std::set<webrtc::MediaStreamTrackInterface *> _known;

    // the observer registration posted by the constructor
    AliveGuard _alive;
  };

} // namespace python_webrtc
