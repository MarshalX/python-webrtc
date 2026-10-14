//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "relayed_video_track.h"

#include <utility>

#include <rtc_base/time_utils.h>

namespace python_webrtc {

  RelayedVideoTrack::RelayedVideoTrack(webrtc::scoped_refptr<webrtc::VideoTrackInterface> track)
      : _track(std::move(track)) {}

  RelayedVideoTrack::~RelayedVideoTrack() {
    RTC_DCHECK(_sinks.empty());
  }

  void RelayedVideoTrack::AddOrUpdateSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink,
                                          const webrtc::VideoSinkWants &wants) {
    RTC_DCHECK_RUN_ON(&_worker);
    auto &restamper = _sinks[sink];
    if (!restamper) {
      restamper = std::make_unique<Restamper>(sink);
    }
    _track->AddOrUpdateSink(restamper.get(), wants);
  }

  void RelayedVideoTrack::RemoveSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) {
    RTC_DCHECK_RUN_ON(&_worker);
    auto node = _sinks.extract(sink);
    if (!node.empty()) {
      _track->RemoveSink(node.mapped().get());
    }
  }

  void RelayedVideoTrack::Restamper::OnFrame(const webrtc::VideoFrame &frame) {
    webrtc::VideoFrame restamped = frame;
    restamped.set_timestamp_us(_aligner.TranslateTimestamp(frame.timestamp_us(), webrtc::TimeMicros()));
    restamped.set_ntp_time_ms(0);
    _sink->OnFrame(restamped);
  }

} // namespace python_webrtc
