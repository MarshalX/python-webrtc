//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_CODECS_VIDEOTOOLBOX_H_
#define PYTHON_WEBRTC_CODECS_VIDEOTOOLBOX_H_

#ifdef __APPLE__

#include <api/environment/environment.h>
#include <api/video_codecs/scalability_mode.h>
#include <api/video_codecs/sdp_video_format.h>
#include <api/video_codecs/video_decoder.h>
#include <api/video_codecs/video_encoder.h>

#include <memory>
#include <vector>

namespace python_webrtc {

  // H.264 through the OS's VideoToolbox (libwebrtc's ObjC SDK codecs)
  struct VideoToolboxEncoderAdapter {
    static std::vector<webrtc::SdpVideoFormat> SupportedFormats();
    static std::unique_ptr<webrtc::VideoEncoder> CreateEncoder(const webrtc::Environment &env,
                                                               const webrtc::SdpVideoFormat &format);
    static bool IsScalabilityModeSupported(webrtc::ScalabilityMode mode);
  };

  struct VideoToolboxDecoderAdapter {
    static std::vector<webrtc::SdpVideoFormat> SupportedFormats();
    static std::unique_ptr<webrtc::VideoDecoder> CreateDecoder(const webrtc::Environment &env,
                                                               const webrtc::SdpVideoFormat &format);
  };

} // namespace python_webrtc

#endif // __APPLE__

#endif // PYTHON_WEBRTC_CODECS_VIDEOTOOLBOX_H_
