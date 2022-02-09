//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_audio_track_source.h"

namespace python_webrtc {

  RTCAudioTrackSource::~RTCAudioTrackSource() {
    PeerConnectionFactory::Release();
    _factory = nullptr;
  }

  webrtc::MediaSourceInterface::SourceState RTCAudioTrackSource::state() const {
    return webrtc::MediaSourceInterface::SourceState::kLive;
  }

  bool RTCAudioTrackSource::remote() const {
    return false;
  }

  void RTCAudioTrackSource::AddSink(webrtc::AudioTrackSinkInterface *sink) {
    _sink = sink;
  }

  void RTCAudioTrackSource::RemoveSink(webrtc::AudioTrackSinkInterface *) {
    _sink = nullptr;
  }

  void RTCAudioTrackSource::PushData(RTCOnDataEvent &data) {
    webrtc::AudioTrackSinkInterface *sink = _sink;
    if (sink) {
      sink->OnData(
          data.audioData,
          data.bitsPerSample,
          data.sampleRate,
          data.channelCount,
          data.numberOfFrames
      );
    }
  }

} // namespace python_webrtc
