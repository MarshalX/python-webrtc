//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "openh264_decoder.h"

#include <api/video/i420_buffer.h>
#include <api/video/video_frame.h>
#include <modules/video_coding/include/video_error_codes.h>
#include <third_party/openh264/src/codec/api/wels/codec_api.h>

#include <optional>

namespace python_webrtc {

  OpenH264Decoder::~OpenH264Decoder() {
    Release();
  }

  bool OpenH264Decoder::Configure(const Settings &settings) {
    Release();
    if (WelsCreateDecoder(&_decoder) != 0 || !_decoder) {
      _decoder = nullptr;
      return false;
    }

    int traceLevel = WELS_LOG_QUIET;
    _decoder->SetOption(DECODER_OPTION_TRACE_LEVEL, &traceLevel);

    SDecodingParam param{};
    // a concealed picture is garbage to the viewer, an error makes libwebrtc ask for a key frame
    param.eEcActiveIdc = ERROR_CON_DISABLE;
    param.sVideoProperty.size = sizeof(param.sVideoProperty);
    param.sVideoProperty.eVideoBsType = VIDEO_BITSTREAM_AVC;
    if (_decoder->Initialize(&param) != 0) {
      Release();
      return false;
    }
    return true;
  }

  int32_t OpenH264Decoder::Decode(const webrtc::EncodedImage &image, int64_t renderTimeMs) {
    if (!_decoder || !_callback) {
      return WEBRTC_VIDEO_CODEC_UNINITIALIZED;
    }
    if (!image.data() || image.size() == 0) {
      return WEBRTC_VIDEO_CODEC_ERR_PARAMETER;
    }

    unsigned char *planes[3] = {};
    SBufferInfo info{};
    const auto state = _decoder->DecodeFrameNoDelay(image.data(), static_cast<int>(image.size()), planes, &info);
    if (state != dsErrorFree) {
      return WEBRTC_VIDEO_CODEC_ERROR;
    }
    if (info.iBufferStatus != 1) {
      // parameter sets only, or a frame still waiting for its slices
      return WEBRTC_VIDEO_CODEC_OK;
    }

    const auto &picture = info.UsrData.sSystemBuffer;
    const auto buffer = webrtc::I420Buffer::Copy(picture.iWidth, picture.iHeight, planes[0], picture.iStride[0],
                                                 planes[1], picture.iStride[1], planes[2], picture.iStride[1]);
    auto frame = webrtc::VideoFrame::Builder()
                     .set_video_frame_buffer(buffer)
                     .set_rtp_timestamp(image.RtpTimestamp())
                     .set_color_space(image.ColorSpace())
                     .build();
    _callback->Decoded(frame, std::nullopt, std::nullopt);
    return WEBRTC_VIDEO_CODEC_OK;
  }

  int32_t OpenH264Decoder::RegisterDecodeCompleteCallback(webrtc::DecodedImageCallback *callback) {
    _callback = callback;
    return WEBRTC_VIDEO_CODEC_OK;
  }

  int32_t OpenH264Decoder::Release() {
    if (_decoder) {
      _decoder->Uninitialize();
      WelsDestroyDecoder(_decoder);
      _decoder = nullptr;
    }
    return WEBRTC_VIDEO_CODEC_OK;
  }

  webrtc::VideoDecoder::DecoderInfo OpenH264Decoder::GetDecoderInfo() const {
    DecoderInfo info;
    info.implementation_name = ImplementationName();
    return info;
  }

  const char *OpenH264Decoder::ImplementationName() const {
    return "OpenH264";
  }

} // namespace python_webrtc
