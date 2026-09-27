//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>
#include <pc/local_audio_source.h>

#include "rtc_audio_track_source.h"
#include "media_stream_track.h"

namespace python_webrtc {

  class RTCAudioSource {
  public:
    RTCAudioSource();

    static void Init(pybind11::module &m);

    MediaStreamTrack *CreateTrack();

    void OnData(RTCOnDataEvent &);

  private:
    webrtc::scoped_refptr<RTCAudioTrackSource> _source;
  };

} // namespace python_webrtc
