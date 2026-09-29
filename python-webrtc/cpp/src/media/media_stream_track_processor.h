//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <optional>
#include <variant>
#include <vector>

#include <api/media_stream_interface.h>
#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>

#include <pybind11/pybind11.h>

#include "../utils/alive_count.h"
#include "video_frame_buffer.h"
#include "wakeup.h"
#include "../interfaces/media_stream_track.h"
#include "../utils/listeners.h"

namespace python_webrtc {

  // Queues the media of a track for Python (webrtc.MediaStreamTrackProcessor), which is woken with "_ready"
  class MediaStreamTrackProcessor : public Listeners,
                                    public Wakeable,
                                    public TrackEndObserver,
                                    public webrtc::VideoSinkInterface<webrtc::VideoFrame>,
                                    public webrtc::AudioTrackSinkInterface,
                                    public std::enable_shared_from_this<MediaStreamTrackProcessor> {
  public:
    static std::shared_ptr<MediaStreamTrackProcessor> Create(std::shared_ptr<MediaStreamTrack> track,
                                                             size_t maxBufferSize);

    ~MediaStreamTrackProcessor() override;

    static void Init(pybind11::module &m);

    // the oldest media queued: (VideoFrameBuffer, timestampUs, rotation, rtpTimestamp) or
    // (bytes, bitsPerSample, sampleRate, channels, frames, timestampUs), or None
    pybind11::object Read();

    // stops receiving media, dropping what's queued
    void Cancel();

    // Python got the wakeup: the next media wakes it again (one wakeup at most is on its way)
    void AckWakeup();

    bool GetEnded();

    uint64_t GetTotalFrames() { return _totalFrames; }

    uint64_t GetDiscardedFrames() { return _discardedFrames; }

    // VideoSinkInterface
    void OnFrame(const webrtc::VideoFrame &frame) override;

    // AudioTrackSinkInterface
    void OnData(const void *audioData, int bitsPerSample, int sampleRate, size_t channels, size_t frames) override;

    void OnData(const void *audioData, int bitsPerSample, int sampleRate, size_t channels, size_t frames,
                std::optional<int64_t> absoluteCaptureTimestampMs) override;

    // Wakeable
    void OnWakeup() override;

    // TrackEndObserver
    void OnTrackEnded() override;

  private:
    MediaStreamTrackProcessor(std::shared_ptr<PeerConnectionFactory> factory,
                              webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track, size_t maxBufferSize);

    void Attach();

    void Detach();

    struct VideoItem {
      webrtc::scoped_refptr<webrtc::VideoFrameBuffer> buffer;
      int64_t timestampUs;
      int rotation;
      // of a received frame, 0 for a local one
      uint32_t rtpTimestamp;
    };

    struct AudioItem {
      std::vector<uint8_t> data;
      int bitsPerSample;
      int sampleRate;
      size_t channels;
      size_t frames;
      int64_t timestampUs;
    };

    using Item = std::variant<VideoItem, AudioItem>;

    void Push(Item item);

    // wakes Python, unless a wakeup is pending
    void WakeLocked();

    AliveCount<MediaStreamTrackProcessor> _counted;
    // the threads of the factory run the proxy of the track
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> _track;
    const bool _video;
    const size_t _maxBufferSize;

    std::mutex _mutex;
    std::deque<Item> _queue;
    bool _ended = false;
    // a wakeup is on its way to Python
    bool _wakePending = false;
    std::atomic<uint64_t> _totalFrames = 0;
    std::atomic<uint64_t> _discardedFrames = 0;

    // the sink is registered with the track; changed by Python and the destructor only
    std::mutex _attachMutex;
    bool _attached = false;
  };

} // namespace python_webrtc
