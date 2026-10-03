//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_CODECS_OPENH264_H_
#define PYTHON_WEBRTC_CODECS_OPENH264_H_

#include <api/environment/environment.h>
#include <api/video_codecs/scalability_mode.h>
#include <api/video_codecs/sdp_video_format.h>
#include <api/video_codecs/video_decoder.h>
#include <api/video_codecs/video_encoder.h>
#include <pybind11/pybind11.h>

#include <memory>
#include <vector>

namespace python_webrtc {

  // Cisco's OpenH264 binary, loaded at runtime: H.264 is offered only while it's enabled
  class OpenH264 {
  public:
    static bool Enabled();

    static void Init(pybind11::module &m);
  };

  struct OpenH264EncoderAdapter {
    static std::vector<webrtc::SdpVideoFormat> SupportedFormats();
    static std::unique_ptr<webrtc::VideoEncoder> CreateEncoder(const webrtc::Environment &env,
                                                               const webrtc::SdpVideoFormat &format);
    static bool IsScalabilityModeSupported(webrtc::ScalabilityMode mode);
  };

  struct OpenH264DecoderAdapter {
    static std::vector<webrtc::SdpVideoFormat> SupportedFormats();
    static std::unique_ptr<webrtc::VideoDecoder> CreateDecoder(const webrtc::Environment &env,
                                                               const webrtc::SdpVideoFormat &format);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_CODECS_OPENH264_H_
