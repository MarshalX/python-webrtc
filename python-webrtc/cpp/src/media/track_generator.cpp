//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "track_generator.h"

#include <cstring>
#include <string_view>

#include <api/video/video_frame.h>
#include <rtc_base/crypto_random.h>
#include <system_wrappers/include/clock.h>

#include "../exceptions.h"
#include "../utils/gil.h"

namespace python_webrtc {

  namespace {

    // libwebrtc takes audio in 10 ms frames
    constexpr int kAudioFramesPerSecond = 100;

  } // namespace

  TrackGenerator::TrackGenerator(const std::string &kind)
      : _factory(PeerConnectionFactory::GetOrCreateDefault()), _video(kind == "video") {
    if (kind != "video" && kind != "audio") {
      throw pybind11::type_error("The kind must be 'audio' or 'video', not '" + kind + "'");
    }
    webrtc::scoped_refptr<webrtc::MediaStreamTrackInterface> track;
    if (_video) {
      _videoSource = webrtc::make_ref_counted<RTCVideoTrackSource>(false, std::nullopt);
      track = _factory->factory()->CreateVideoTrack(_videoSource, webrtc::CreateRandomUuid());
    } else {
      _audioSource = webrtc::make_ref_counted<RTCAudioTrackSource>();
      track = _factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), _audioSource.get());
    }
    _track = MediaStreamTrack::holder().GetOrCreate(_factory, track);
  }

  void TrackGenerator::Init(pybind11::module &m) {
    pybind11::class_<TrackGenerator, std::shared_ptr<TrackGenerator>>(m, "TrackGenerator")
        .def(pybind11::init<const std::string &>(), nogil(), pybind11::arg("kind"))
        .def_property_readonly("track", &TrackGenerator::GetTrack)
        .def_property_readonly("kind", &TrackGenerator::GetKind)
        .def_property_readonly("live", nogil_fn(&TrackGenerator::GetLive))
        .def_property("muted", nogil_fn(&TrackGenerator::GetMuted), nogil_fn(&TrackGenerator::SetMuted))
        .def("writeVideo", &TrackGenerator::WriteVideo, nogil(), pybind11::arg("buffer"),
             pybind11::arg("timestampUs"), pybind11::arg("rotation"))
        .def("writeAudio", &TrackGenerator::WriteAudio, pybind11::arg("samples"), pybind11::arg("sampleRate"),
             pybind11::arg("channels"), pybind11::arg("frames"))
        .def("close", &TrackGenerator::Close, nogil());
  }

  bool TrackGenerator::GetLive() {
    return _track->active();
  }

  bool TrackGenerator::GetMuted() {
    return _muted;
  }

  void TrackGenerator::SetMuted(bool muted) {
    _muted = muted;
    _track->SetMuted(muted);
  }

  void TrackGenerator::WriteVideo(const std::shared_ptr<VideoFrameBuffer> &buffer, int64_t timestampUs,
                                  int rotation) {
    if (!_video) {
      throw pybind11::type_error("An audio generator takes AudioData");
    }
    if (!GetLive() || _muted) {
      return;
    }
    // sinks see the timestamp of the application, encoders take the capture time from the NTP one
    auto frame = webrtc::VideoFrame::Builder()
                     .set_video_frame_buffer(buffer->ToWebrtc())
                     .set_timestamp_us(timestampUs)
                     .set_ntp_time_ms(webrtc::Clock::GetRealTimeClock()->CurrentNtpInMilliseconds())
                     .set_rotation(static_cast<webrtc::VideoRotation>(rotation))
                     .build();
    _videoSource->PushFrame(frame);
  }

  void TrackGenerator::WriteAudio(const pybind11::bytes &samples, int sampleRate, size_t channels, size_t frames) {
    if (_video) {
      throw pybind11::type_error("A video generator takes VideoFrame");
    }
    std::string_view data = samples;
    if (data.size() != frames * channels * sizeof(int16_t)) {
      throw pybind11::value_error("The samples don't have the given number of frames");
    }
    pybind11::gil_scoped_release release;
    if (!GetLive() || _muted) {
      return;
    }
    std::lock_guard<std::mutex> lock(_audioMutex);
    if (sampleRate != _pendingRate || channels != _pendingChannels) {
      _pending.clear();
      _pendingRate = sampleRate;
      _pendingChannels = channels;
    }
    size_t offset = _pending.size();
    _pending.resize(offset + frames * channels);
    std::memcpy(_pending.data() + offset, data.data(), data.size());

    size_t chunkFrames = static_cast<size_t>(sampleRate / kAudioFramesPerSecond);
    size_t chunk = chunkFrames * channels;
    size_t sent = 0;
    while (chunk > 0 && _pending.size() - sent >= chunk) {
      _audioSource->PushSamples(_pending.data() + sent, sizeof(int16_t) * 8, sampleRate, channels, chunkFrames);
      sent += chunk;
    }
    _pending.erase(_pending.begin(), _pending.begin() + static_cast<std::ptrdiff_t>(sent));
  }

  void TrackGenerator::Close() {
    // the tracks observe their source on the signaling thread
    _factory->_signalingThread->BlockingCall([this]() {
      if (_video) {
        _videoSource->End();
      } else {
        _audioSource->End();
      }
    });
  }

} // namespace python_webrtc
