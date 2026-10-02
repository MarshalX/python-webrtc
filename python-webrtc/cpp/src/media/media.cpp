//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media.h"

#include "audio_samples.h"
#include "encoded_frame.h"
#include "frame_transformer_bridge.h"
#include "media_stream_track_processor.h"
#include "rtc_rtp_script_transform.h"
#include "sframe_transform.h"
#include "track_generator.h"
#include "video_frame_buffer.h"

namespace python_webrtc {

  void Media::Init(pybind11::module &m) {
    VideoFrameBuffer::Init(m);
    AudioSamples::Init(m);
    MediaStreamTrackProcessor::Init(m);
    TrackGenerator::Init(m);
    RtpTransform::Init(m);
    EncodedFrame::Init(m);
    RTCRtpScriptTransform::Init(m);
    SFrameTransform::Init(m);
  }

} // namespace python_webrtc
