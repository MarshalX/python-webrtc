//
// Created by Il'ya Semyonov on 1/14/22.
//

#pragma once

#include <webrtc/api/media_stream_interface.h>
#include <webrtc/api/scoped_refptr.h>
#include <webrtc/pc/local_audio_source.h>

#include "rtc_audio_track_source.h"
#include "media_stream_track.h"

namespace python_webrtc {

  class RTCAudioSource {
  public:
    RTCAudioSource();

    static void Init(pybind11::module &m);

    std::unique_ptr<MediaStreamTrack> CreateTrack();

    void OnData(RTCOnDataEvent &);

  private:
    rtc::scoped_refptr<RTCAudioTrackSource> _source;
  };

} // namespace python_webrtc
