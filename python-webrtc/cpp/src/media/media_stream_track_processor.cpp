//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_stream_track_processor.h"

#include <algorithm>
#include <cstring>

#include <rtc_base/time_utils.h>

#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  MediaStreamTrackProcessor::MediaStreamTrackProcessor(std::shared_ptr<MediaStreamTrack> track, size_t maxBufferSize)
      : _track(std::move(track)),
        _video(_track->track()->kind() == webrtc::MediaStreamTrackInterface::kVideoKind),
        _maxBufferSize(std::max<size_t>(1, maxBufferSize)) {}

  std::shared_ptr<MediaStreamTrackProcessor> MediaStreamTrackProcessor::Create(std::shared_ptr<MediaStreamTrack> track,
                                                                               size_t maxBufferSize) {
    std::shared_ptr<MediaStreamTrackProcessor> processor(
        new MediaStreamTrackProcessor(std::move(track), maxBufferSize), DeleteOffLibwebrtcThread());
    processor->Attach();
    // after the sink is attached: an end meanwhile detaches it
    processor->_track->AddEndObserver(processor);
    return processor;
  }

  MediaStreamTrackProcessor::~MediaStreamTrackProcessor() {
    BlockingDestructor release("MediaStreamTrackProcessor");
    Detach();
    DropListeners();
  }

  void MediaStreamTrackProcessor::Init(pybind11::module &m) {
    Listeners::BindClass<MediaStreamTrackProcessor>(m, "MediaStreamTrackProcessor")
        .def(pybind11::init(&MediaStreamTrackProcessor::Create), nogil(), pybind11::arg("track"),
             pybind11::arg("maxBufferSize"))
        .def("read", &MediaStreamTrackProcessor::Read)
        .def("cancel", &MediaStreamTrackProcessor::Cancel, nogil())
        .def("_ackWakeup", &MediaStreamTrackProcessor::AckWakeup, nogil())
        .def_property_readonly("ended", nogil_fn(&MediaStreamTrackProcessor::GetEnded))
        .def_property_readonly("totalFrames", &MediaStreamTrackProcessor::GetTotalFrames)
        .def_property_readonly("discardedFrames", &MediaStreamTrackProcessor::GetDiscardedFrames);
  }

  void MediaStreamTrackProcessor::Attach() {
    std::lock_guard<std::mutex> lock(_attachMutex);
    if (_attached || _track->ended()) {
      return;
    }
    if (_video) {
      static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(*_track)->AddOrUpdateSink(
          this, webrtc::VideoSinkWants());
    } else {
      static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(*_track)->AddSink(this);
    }
    _attached = true;
  }

  void MediaStreamTrackProcessor::Detach() {
    std::lock_guard<std::mutex> lock(_attachMutex);
    if (!_attached) {
      return;
    }
    // once removed, the track doesn't call the sink anymore
    if (_video) {
      static_cast<webrtc::scoped_refptr<webrtc::VideoTrackInterface>>(*_track)->RemoveSink(this);
    } else {
      static_cast<webrtc::scoped_refptr<webrtc::AudioTrackInterface>>(*_track)->RemoveSink(this);
    }
    _attached = false;
  }

  void MediaStreamTrackProcessor::Push(Item item) {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_ended) {
      return;
    }
    _totalFrames++;
    while (_queue.size() >= _maxBufferSize) {
      _queue.pop_front();
      _discardedFrames++;
    }
    _queue.push_back(std::move(item));
    WakeLocked();
  }

  void MediaStreamTrackProcessor::WakeLocked() {
    if (!_wakePending) {
      _wakePending = true;
      Wakeup::Post(weak_from_this());
    }
  }

  void MediaStreamTrackProcessor::OnFrame(const webrtc::VideoFrame &frame) {
    Push(VideoItem{frame.video_frame_buffer(), frame.timestamp_us(), static_cast<int>(frame.rotation()),
                   frame.rtp_timestamp()});
  }

  void MediaStreamTrackProcessor::OnData(const void *audioData, int bitsPerSample, int sampleRate, size_t channels,
                                         size_t frames) {
    OnData(audioData, bitsPerSample, sampleRate, channels, frames, std::nullopt);
  }

  void MediaStreamTrackProcessor::OnData(const void *audioData, int bitsPerSample, int sampleRate, size_t channels,
                                         size_t frames, std::optional<int64_t> absoluteCaptureTimestampMs) {
    size_t size = frames * channels * (bitsPerSample / 8);
    std::vector<uint8_t> data(size);
    std::memcpy(data.data(), audioData, size);
    Push(AudioItem{std::move(data), bitsPerSample, sampleRate, channels, frames, webrtc::TimeMicros()});
  }

  void MediaStreamTrackProcessor::OnWakeup() {
    Emit("_ready");
  }

  void MediaStreamTrackProcessor::OnTrackEnded() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_ended) {
      return;
    }
    _ended = true;
    _queue.clear();
    // the end wakes Python even while a wakeup is pending
    _wakePending = false;
    WakeLocked();
  }

  void MediaStreamTrackProcessor::Cancel() {
    {
      std::lock_guard<std::mutex> lock(_mutex);
      _ended = true;
      _queue.clear();
    }
    Detach();
  }

  void MediaStreamTrackProcessor::AckWakeup() {
    std::lock_guard<std::mutex> lock(_mutex);
    _wakePending = false;
  }

  bool MediaStreamTrackProcessor::GetEnded() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _ended && _queue.empty();
  }

  pybind11::object MediaStreamTrackProcessor::Read() {
    std::optional<Item> item;
    bool ended;
    {
      pybind11::gil_scoped_release release;
      std::lock_guard<std::mutex> lock(_mutex);
      if (!_queue.empty()) {
        item = std::move(_queue.front());
        _queue.pop_front();
      }
      ended = _ended;
    }
    if (ended && !item) {
      // the sink is detached here rather than on the thread that ended the track
      pybind11::gil_scoped_release release;
      Detach();
    }
    if (!item) {
      return pybind11::none();
    }
    if (auto video = std::get_if<VideoItem>(&*item)) {
      std::shared_ptr<VideoFrameBuffer> buffer;
      {
        pybind11::gil_scoped_release release;
        buffer = VideoFrameBuffer::FromWebrtc(video->buffer);
      }
      return pybind11::make_tuple(buffer, video->timestampUs, video->rotation, video->rtpTimestamp);
    }
    auto &audio = std::get<AudioItem>(*item);
    pybind11::bytes data(reinterpret_cast<const char *>(audio.data.data()), audio.data.size());
    return pybind11::make_tuple(data, audio.bitsPerSample, audio.sampleRate, audio.channels, audio.frames,
                                audio.timestampUs);
  }

} // namespace python_webrtc
