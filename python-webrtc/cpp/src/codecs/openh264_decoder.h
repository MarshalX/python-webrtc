//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_CODECS_OPENH264_DECODER_H_
#define PYTHON_WEBRTC_CODECS_OPENH264_DECODER_H_

#include <api/video/encoded_image.h>
#include <api/video_codecs/video_decoder.h>

class ISVCDecoder;

namespace python_webrtc {

  class OpenH264Decoder : public webrtc::VideoDecoder {
  public:
    OpenH264Decoder() = default;
    ~OpenH264Decoder() override;

    OpenH264Decoder(const OpenH264Decoder &) = delete;
    OpenH264Decoder &operator=(const OpenH264Decoder &) = delete;
    OpenH264Decoder(OpenH264Decoder &&) = delete;
    OpenH264Decoder &operator=(OpenH264Decoder &&) = delete;

    bool Configure(const Settings &settings) override;
    int32_t Decode(const webrtc::EncodedImage &image, int64_t renderTimeMs) override;
    int32_t RegisterDecodeCompleteCallback(webrtc::DecodedImageCallback *callback) override;
    int32_t Release() override;
    [[nodiscard]] DecoderInfo GetDecoderInfo() const override;
    [[nodiscard]] const char *ImplementationName() const override;

  private:
    void Destroy();

    ISVCDecoder *_decoder = nullptr;
    webrtc::DecodedImageCallback *_callback = nullptr;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_CODECS_OPENH264_DECODER_H_
