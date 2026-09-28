//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <optional>
#include <string>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_video_track_source.h"

namespace python_webrtc {

  // Video an application produces, as tracks (webrtc.RTCVideoSource)
  class RTCVideoSource {
  public:
    RTCVideoSource(bool isScreencast, std::optional<bool> needsDenoising);

    static void Init(pybind11::module &m);

    std::shared_ptr<MediaStreamTrack> CreateTrack();

    // an I420 frame: the Y plane, then the U and V ones, without padding
    void OnFrame(int width, int height, const std::string &i420, int rotation, std::optional<int64_t> timestampUs);

    // a video track of the synthetic camera, for get_user_media
    static std::shared_ptr<MediaStreamTrack> CreateCameraTrack(
        const std::shared_ptr<PeerConnectionFactory> &factory, int width, int height, double frameRate);

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<RTCVideoTrackSource> _source;
  };

} // namespace python_webrtc
