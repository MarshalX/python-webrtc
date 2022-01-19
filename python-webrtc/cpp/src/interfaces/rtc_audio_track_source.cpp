//
// Created by Il'ya Semyonov on 1/14/22.
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
