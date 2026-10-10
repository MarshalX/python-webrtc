//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_TRACK_GENERATOR_H_
#define PYTHON_WEBRTC_MEDIA_TRACK_GENERATOR_H_

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../interfaces/media_stream_track.h"
#include "../interfaces/peer_connection_factory.h"
#include "../interfaces/rtc_audio_track_source.h"
#include "../interfaces/rtc_video_track_source.h"
#include "../utils/native_object.h"
#include "video_frame_buffer.h"

namespace python_webrtc {

  // The source of a track fed with frames by Python (webrtc.VideoTrackGenerator, webrtc.MediaStreamTrackGenerator)
  class TrackGenerator : public NativeObject<TrackGenerator> {
  public:
    static constexpr const char *kName = "TrackGenerator";

    explicit TrackGenerator(const std::string &kind);

    static void Init(pybind11::module &m);

    std::shared_ptr<MediaStreamTrack> GetTrack() { return _track; }

    std::string GetKind() const { return _video ? "video" : "audio"; }

    // false once the generator or all its tracks ended
    bool GetLive();

    bool GetMuted();

    void SetMuted(bool muted);

    void WriteVideo(const std::shared_ptr<VideoFrameBuffer> &buffer, int64_t timestampUs, int rotation);

    // interleaved 16-bit samples, sent in 10 ms frames
    void WriteAudio(const pybind11::bytes &samples, int sampleRate, size_t channels, size_t frames);

    // ends the track
    void Close();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    const bool _video;
    webrtc::scoped_refptr<RTCVideoTrackSource> _videoSource;
    webrtc::scoped_refptr<RTCAudioTrackSource> _audioSource;
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<SourceControl> _control = std::make_shared<SourceControl>();
    std::atomic<bool> _muted = false;

    // samples short of a 10 ms frame, sent with the next ones of the same format
    std::mutex _audioMutex;
    std::vector<int16_t> _pending;
    int _pendingRate = 0;
    size_t _pendingChannels = 0;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_TRACK_GENERATOR_H_
