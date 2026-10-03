//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_H_
#define PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_H_

#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../utils/alive_guard.h"
#include "../utils/listeners.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // Emits addtrack and removetrack when libwebrtc changes the tracks of a remote stream
  class MediaStream : public webrtc::ObserverInterface, public Listeners {
  public:
    MediaStream(std::shared_ptr<PeerConnectionFactory> factory,
                webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream);

    ~MediaStream() override;

    MediaStream(const MediaStream &) = delete;
    MediaStream &operator=(const MediaStream &) = delete;

    // ObserverInterface, on the signaling thread
    void OnChanged() override;

    static void Init(pybind11::module &m);

    // A new stream of these tracks (new MediaStream() in a browser)
    static std::shared_ptr<MediaStream> Create(const std::vector<std::shared_ptr<MediaStreamTrack>> &tracks);

    static InstanceHolder<MediaStream, webrtc::MediaStreamInterface> &holder();

    webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream();

    std::string GetId();

    bool GetActive();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetAudioTracks();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetVideoTracks();

    std::vector<std::shared_ptr<MediaStreamTrack>> GetTracks();

    std::optional<std::shared_ptr<MediaStreamTrack>> GetTrackById(const std::string &id);

    void AddTrack(const std::shared_ptr<MediaStreamTrack> &mediaStreamTrack);

    void RemoveTrack(MediaStreamTrack &mediaStreamTrack);

    std::shared_ptr<MediaStream> Clone();

  private:
    std::vector<webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface>> tracks();

    // wrappers of the current tracks of the stream; the stream owns them, so their state outlives Python references
    std::vector<std::shared_ptr<MediaStreamTrack>> SyncTracks();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::MediaStreamInterface> _stream;

    std::mutex _tracksMutex;
    // the tracks the stream had when last notified, or as Python changed them, guarded by _tracksMutex
    std::set<webrtc::MediaStreamTrackInterface *> _known;

    // see AliveGuard
    AliveGuard _alive;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_MEDIA_STREAM_H_
