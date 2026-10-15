//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_CODECS_VIDEO_CODEC_FACTORIES_H_
#define PYTHON_WEBRTC_CODECS_VIDEO_CODEC_FACTORIES_H_

#include <api/video_codecs/video_decoder_factory.h>
#include <api/video_codecs/video_encoder_factory.h>

#include <memory>

namespace python_webrtc {

  std::unique_ptr<webrtc::VideoEncoderFactory> CreateVideoEncoderFactory();

  std::unique_ptr<webrtc::VideoDecoderFactory> CreateVideoDecoderFactory();

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_CODECS_VIDEO_CODEC_FACTORIES_H_
