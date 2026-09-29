//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"
#include "video_frame_buffer.h"
#include "../interfaces/media_stream_track.h"
#include "../interfaces/peer_connection_factory.h"
#include "../interfaces/rtc_audio_track_source.h"
#include "../interfaces/rtc_video_track_source.h"

namespace python_webrtc {

  // The source of a track fed with frames by Python (webrtc.VideoTrackGenerator, webrtc.MediaStreamTrackGenerator)
  class TrackGenerator {
  public:
    explicit TrackGenerator(const std::string &kind);

    // deleted without the GIL: the track's proxy is destroyed on the signaling thread
    static std::shared_ptr<TrackGenerator> Create(const std::string &kind);

    static void Init(pybind11::module &m);

    // the wrapper of the track, owned by Python once it has it
    std::shared_ptr<MediaStreamTrack> GetTrack();

    std::string GetKind() { return _video ? "video" : "audio"; }

    // whether the track can still take frames: it ends with the generator or with stop()
    bool GetLive();

    bool GetMuted();

    void SetMuted(bool muted);

    void WriteVideo(const std::shared_ptr<VideoFrameBuffer> &buffer, int64_t timestampUs, int rotation);

    // interleaved 16-bit samples, sent in 10 ms frames
    void WriteAudio(const pybind11::bytes &samples, int sampleRate, size_t channels, size_t frames);

    // ends the track
    void Close();

  private:
    // whether the track ended, kept when its wrapper is gone
    struct EndState : TrackEndObserver {
      std::atomic<bool> ended = false;

      void OnTrackEnded() override {
        ended = true;
      }
    };

    AliveCount<TrackGenerator> _counted;
    std::shared_ptr<PeerConnectionFactory> _factory;
    const bool _video;
    webrtc::scoped_refptr<RTCVideoTrackSource> _videoSource;
    webrtc::scoped_refptr<RTCAudioTrackSource> _audioSource;
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> _webrtcTrack;
    // weak once Python has it: an audio generator is its own track, a strong one hides a cycle from the collector
    std::mutex _trackMutex;
    std::shared_ptr<MediaStreamTrack> _initialTrack;
    std::weak_ptr<MediaStreamTrack> _track;
    std::shared_ptr<EndState> _endState = std::make_shared<EndState>();
    std::atomic<bool> _muted = false;

    // samples short of a 10 ms frame, sent with the next ones of the same format
    std::mutex _audioMutex;
    std::vector<int16_t> _pending;
    int _pendingRate = 0;
    size_t _pendingChannels = 0;
  };

} // namespace python_webrtc
