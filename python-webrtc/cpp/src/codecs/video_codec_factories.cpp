//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "video_codec_factories.h"
#include "openh264.h"
#include "videotoolbox.h"

#include <api/video_codecs/video_decoder_factory_template.h>
#include <api/video_codecs/video_decoder_factory_template_dav1d_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp9_adapter.h>
#include <api/video_codecs/video_encoder_factory_template.h>
#include <api/video_codecs/video_encoder_factory_template_libaom_av1_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp9_adapter.h>
#include <media/engine/simulcast_encoder_adapter.h>

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace python_webrtc {

  namespace {

#ifdef __APPLE__
    // the OS's H.264 first, it wins the formats both offer
    using Encoders = webrtc::VideoEncoderFactoryTemplate<
        webrtc::LibvpxVp8EncoderTemplateAdapter, webrtc::LibvpxVp9EncoderTemplateAdapter,
        webrtc::LibaomAv1EncoderTemplateAdapter, VideoToolboxEncoderAdapter, OpenH264EncoderAdapter>;

    using Decoders = webrtc::VideoDecoderFactoryTemplate<
        webrtc::LibvpxVp8DecoderTemplateAdapter, webrtc::LibvpxVp9DecoderTemplateAdapter,
        webrtc::Dav1dDecoderTemplateAdapter, VideoToolboxDecoderAdapter, OpenH264DecoderAdapter>;
#else
    // H.264 only once Cisco's OpenH264 binary is loaded (the prebuilts have none)
    using Encoders =
        webrtc::VideoEncoderFactoryTemplate<webrtc::LibvpxVp8EncoderTemplateAdapter,
                                            webrtc::LibvpxVp9EncoderTemplateAdapter,
                                            webrtc::LibaomAv1EncoderTemplateAdapter, OpenH264EncoderAdapter>;

    using Decoders = webrtc::VideoDecoderFactoryTemplate<webrtc::LibvpxVp8DecoderTemplateAdapter,
                                                         webrtc::LibvpxVp9DecoderTemplateAdapter,
                                                         webrtc::Dav1dDecoderTemplateAdapter, OpenH264DecoderAdapter>;
#endif

    // as libwebrtc's builtin factory: with one layer, the adapter passes the encoder through
    class SimulcastEncoderFactory : public webrtc::VideoEncoderFactory {
    public:
      [[nodiscard]] std::vector<webrtc::SdpVideoFormat> GetSupportedFormats() const override {
        return _encoders.GetSupportedFormats();
      }

      [[nodiscard]] CodecSupport QueryCodecSupport(const webrtc::SdpVideoFormat &format,
                                                   std::optional<std::string> scalabilityMode,
                                                   std::optional<webrtc::Resolution> resolution) const override {
        return _encoders.QueryCodecSupport(format, std::move(scalabilityMode), resolution);
      }

      std::unique_ptr<webrtc::VideoEncoder> Create(const webrtc::Environment &env,
                                                   const webrtc::SdpVideoFormat &format) override {
        if (!format.IsCodecInList(_encoders.GetSupportedFormats())) {
          return nullptr;
        }
        return std::make_unique<webrtc::SimulcastEncoderAdapter>(env, &_encoders, FallbackFor(format), format);
      }

    private:
#ifdef __APPLE__
      // OpenH264 takes over from VideoToolbox when it fails; the other encoders are software already
      webrtc::VideoEncoderFactory *FallbackFor(const webrtc::SdpVideoFormat &format) {
        if (OpenH264::Enabled() && format.IsCodecInList(VideoToolboxEncoderAdapter::SupportedFormats())) {
          return &_fallback;
        }
        return nullptr;
      }

      webrtc::VideoEncoderFactoryTemplate<OpenH264EncoderAdapter> _fallback;
#else
      static webrtc::VideoEncoderFactory *FallbackFor(const webrtc::SdpVideoFormat & /*format*/) { return nullptr; }
#endif

      Encoders _encoders;
    };

  } // namespace

  std::unique_ptr<webrtc::VideoEncoderFactory> CreateVideoEncoderFactory() {
    return std::make_unique<SimulcastEncoderFactory>();
  }

  std::unique_ptr<webrtc::VideoDecoderFactory> CreateVideoDecoderFactory() {
    return std::make_unique<Decoders>();
  }

} // namespace python_webrtc
