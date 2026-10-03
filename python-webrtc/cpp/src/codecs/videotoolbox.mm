//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "videotoolbox.h"

#include <api/make_ref_counted.h>
#include <api/video/i420_buffer.h>
#include <api/video_codecs/h264_profile_level_id.h>
#import <components/video_codec/RTCVideoDecoderFactoryH264.h>
#import <components/video_codec/RTCVideoEncoderFactoryH264.h>
#import <components/video_frame_buffer/RTCCVPixelBuffer.h>
#include <libyuv/convert.h>
#include <libyuv/convert_from.h>
#include <modules/video_coding/codecs/h264/include/h264.h>
#include <modules/video_coding/include/video_error_codes.h>
#include <native/api/video_decoder_factory.h>
#include <native/api/video_encoder_factory.h>
#include <native/src/objc_frame_buffer.h>

#include <CoreVideo/CoreVideo.h>

#include <atomic>

// The SDK's codecs use full-range NV12, while libwebrtc's I420 is video range: frames are converted both ways here.

namespace {

  // video range: luma in 16-235, chroma in 16-240
  constexpr unsigned kRangeOffset = 16;
  constexpr unsigned kLumaRange = 219;
  constexpr unsigned kChromaRange = 224;
  constexpr unsigned kFullRange = 255;

  // leaked: encoders may outlive static destruction at interpreter exit
  webrtc::VideoEncoderFactory &EncoderFactory() {
    static auto *factory =
        webrtc::ObjCToNativeVideoEncoderFactory([[RTC_OBJC_TYPE(RTCVideoEncoderFactoryH264) alloc] init]).release();
    return *factory;
  }

  webrtc::VideoDecoderFactory &DecoderFactory() {
    static auto *factory =
        webrtc::ObjCToNativeVideoDecoderFactory([[RTC_OBJC_TYPE(RTCVideoDecoderFactoryH264) alloc] init]).release();
    return *factory;
  }

  CVPixelBufferRef PixelBufferOf(webrtc::VideoFrameBuffer &buffer) {
    const auto *objc = dynamic_cast<const webrtc::ObjCFrameBuffer *>(&buffer);
    if (objc == nullptr) {
      return nullptr;
    }
    const id wrapped = objc->wrapped_frame_buffer();
    return [wrapped isKindOfClass:[RTC_OBJC_TYPE(RTCCVPixelBuffer) class]]
               ? static_cast<RTC_OBJC_TYPE(RTCCVPixelBuffer) *>(wrapped).pixelBuffer
               : nullptr;
  }

  class VideoRangeEncoder : public webrtc::VideoEncoder {
  public:
    explicit VideoRangeEncoder(std::unique_ptr<webrtc::VideoEncoder> encoder) : _encoder(std::move(encoder)) {}

    ~VideoRangeEncoder() override { CVPixelBufferPoolRelease(_pool); }

    VideoRangeEncoder(const VideoRangeEncoder &) = delete;
    VideoRangeEncoder &operator=(const VideoRangeEncoder &) = delete;
    VideoRangeEncoder(VideoRangeEncoder &&) = delete;
    VideoRangeEncoder &operator=(VideoRangeEncoder &&) = delete;

    void SetFecControllerOverride(webrtc::FecControllerOverride *override) override {
      _encoder->SetFecControllerOverride(override);
    }

    int InitEncode(const webrtc::VideoCodec *codec, const Settings &settings) override {
      return _encoder->InitEncode(codec, settings);
    }

    int32_t RegisterEncodeCompleteCallback(webrtc::EncodedImageCallback *callback) override {
      return _encoder->RegisterEncodeCompleteCallback(callback);
    }

    int32_t Release() override { return _encoder->Release(); }

    int32_t Encode(const webrtc::VideoFrame &frame, const std::vector<webrtc::VideoFrameType> *types) override {
      @autoreleasepool {
        if (PixelBufferOf(*frame.video_frame_buffer()) != nullptr) {
          return _encoder->Encode(frame, types);
        }
        auto i420 = frame.video_frame_buffer()->ToI420();
        CVPixelBufferRef pixelBuffer = i420 ? Allocate(i420->width(), i420->height()) : nullptr;
        if (pixelBuffer == nullptr) {
          return WEBRTC_VIDEO_CODEC_ERROR;
        }
        if (CVPixelBufferLockBaseAddress(pixelBuffer, 0) != kCVReturnSuccess) {
          CVPixelBufferRelease(pixelBuffer);
          return WEBRTC_VIDEO_CODEC_ERROR;
        }
        libyuv::I420ToNV12(i420->DataY(), i420->StrideY(), i420->DataU(), i420->StrideU(), i420->DataV(),
                           i420->StrideV(), static_cast<uint8_t *>(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0)),
                           static_cast<int>(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)),
                           static_cast<uint8_t *>(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1)),
                           static_cast<int>(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1)), i420->width(),
                           i420->height());
        CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
        CVBufferSetAttachment(pixelBuffer, kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_601_4,
                              kCVAttachmentMode_ShouldPropagate);

        webrtc::VideoFrame converted = frame;
        converted.set_video_frame_buffer(webrtc::make_ref_counted<webrtc::ObjCFrameBuffer>(
            [[RTC_OBJC_TYPE(RTCCVPixelBuffer) alloc] initWithPixelBuffer:pixelBuffer]));
        CVPixelBufferRelease(pixelBuffer);
        return _encoder->Encode(converted, types);
      }
    }

    void SetRates(const RateControlParameters &parameters) override { _encoder->SetRates(parameters); }

    void OnPacketLossRateUpdate(float rate) override { _encoder->OnPacketLossRateUpdate(rate); }

    void OnRttUpdate(int64_t rtt) override { _encoder->OnRttUpdate(rtt); }

    void OnLossNotification(const LossNotification &notification) override {
      _encoder->OnLossNotification(notification);
    }

    [[nodiscard]] EncoderInfo GetEncoderInfo() const override { return _encoder->GetEncoderInfo(); }

  private:
    // a video-range buffer, from a pool recreated when the size changes
    CVPixelBufferRef Allocate(int width, int height) {
      if (_pool == nullptr || width != _width || height != _height) {
        CVPixelBufferPoolRelease(_pool);
        _pool = nullptr;
        NSDictionary *const attributes = @{
          (__bridge NSString *)kCVPixelBufferPixelFormatTypeKey :
              [NSNumber numberWithUnsignedInt:kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange],
          (__bridge NSString *)kCVPixelBufferWidthKey : [NSNumber numberWithInt:width],
          (__bridge NSString *)kCVPixelBufferHeightKey : [NSNumber numberWithInt:height],
          (__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey : @{},
        };
        if (CVPixelBufferPoolCreate(nullptr, nullptr, (__bridge CFDictionaryRef)attributes, &_pool) !=
            kCVReturnSuccess) {
          _pool = nullptr;
          return nullptr;
        }
        _width = width;
        _height = height;
      }
      CVPixelBufferRef pixelBuffer = nullptr;
      CVPixelBufferPoolCreatePixelBuffer(nullptr, _pool, &pixelBuffer);
      return pixelBuffer;
    }

    std::unique_ptr<webrtc::VideoEncoder> _encoder;
    CVPixelBufferPoolRef _pool = nullptr;
    int _width = 0;
    int _height = 0;
  };

  class VideoRangeDecoder : public webrtc::VideoDecoder, public webrtc::DecodedImageCallback {
  public:
    explicit VideoRangeDecoder(std::unique_ptr<webrtc::VideoDecoder> decoder) : _decoder(std::move(decoder)) {}

    bool Configure(const Settings &settings) override { return _decoder->Configure(settings); }

    int32_t Decode(const webrtc::EncodedImage &image, int64_t renderTimeMs) override {
      return _decoder->Decode(image, renderTimeMs);
    }

    int32_t RegisterDecodeCompleteCallback(webrtc::DecodedImageCallback *callback) override {
      _callback = callback;
      return _decoder->RegisterDecodeCompleteCallback(callback != nullptr ? this : nullptr);
    }

    int32_t Release() override { return _decoder->Release(); }

    DecoderInfo GetDecoderInfo() const override { return _decoder->GetDecoderInfo(); }

    const char *ImplementationName() const override { return _decoder->ImplementationName(); }

    int32_t Decoded(webrtc::VideoFrame &frame) override {
      auto *callback = _callback.load();
      return callback != nullptr && Convert(frame) ? callback->Decoded(frame) : WEBRTC_VIDEO_CODEC_ERROR;
    }

    int32_t Decoded(webrtc::VideoFrame &frame, int64_t decodeTimeMs) override {
      auto *callback = _callback.load();
      return callback != nullptr && Convert(frame) ? callback->Decoded(frame, decodeTimeMs) : WEBRTC_VIDEO_CODEC_ERROR;
    }

    void Decoded(webrtc::VideoFrame &frame, std::optional<int32_t> decodeTimeMs,
                 std::optional<uint8_t> quantizer) override {
      auto *callback = _callback.load();
      if (callback != nullptr && Convert(frame)) {
        callback->Decoded(frame, decodeTimeMs, quantizer);
      }
    }

  private:
    // full-range NV12 as video-range I420; false drops the frame
    static bool Convert(webrtc::VideoFrame &frame) {
      CVPixelBufferRef pixelBuffer = PixelBufferOf(*frame.video_frame_buffer());
      if (pixelBuffer == nullptr ||
          CVPixelBufferGetPixelFormatType(pixelBuffer) != kCVPixelFormatType_420YpCbCr8BiPlanarFullRange) {
        return true;
      }
      if (CVPixelBufferLockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly) != kCVReturnSuccess) {
        return false;
      }
      const int width = static_cast<int>(CVPixelBufferGetWidth(pixelBuffer));
      const int height = static_cast<int>(CVPixelBufferGetHeight(pixelBuffer));
      auto i420 = webrtc::I420Buffer::Create(width, height);
      libyuv::NV12ToI420(static_cast<const uint8_t *>(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0)),
                         static_cast<int>(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)),
                         static_cast<const uint8_t *>(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1)),
                         static_cast<int>(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1)), i420->MutableDataY(),
                         i420->StrideY(), i420->MutableDataU(), i420->StrideU(), i420->MutableDataV(), i420->StrideV(),
                         width, height);
      CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
      Compress(i420->MutableDataY(), i420->StrideY(), width, height, kLumaRange);
      Compress(i420->MutableDataU(), i420->StrideU(), i420->ChromaWidth(), i420->ChromaHeight(), kChromaRange);
      Compress(i420->MutableDataV(), i420->StrideV(), i420->ChromaWidth(), i420->ChromaHeight(), kChromaRange);
      frame.set_video_frame_buffer(i420);
      return true;
    }

    // 0-255 onto 16-(16 + range); arithmetic rather than a table, so it vectorizes
    static void Compress(uint8_t *data, int stride, int width, int height, unsigned range) {
      for (int row = 0; row < height; ++row) {
        uint8_t *line = data + (static_cast<ptrdiff_t>(row) * stride);
        for (int column = 0; column < width; ++column) {
          line[column] =
              static_cast<uint8_t>(kRangeOffset + (((line[column] * range) + (kFullRange / 2)) / kFullRange));
        }
      }
    }

    std::unique_ptr<webrtc::VideoDecoder> _decoder;
    // set on the decoding thread, called on VideoToolbox's
    std::atomic<webrtc::DecodedImageCallback *> _callback = nullptr;
  };

} // namespace

namespace python_webrtc {

  std::vector<webrtc::SdpVideoFormat> VideoToolboxEncoderAdapter::SupportedFormats() {
    return EncoderFactory().GetSupportedFormats();
  }

  std::unique_ptr<webrtc::VideoEncoder>
  VideoToolboxEncoderAdapter::CreateEncoder(const webrtc::Environment &env, const webrtc::SdpVideoFormat &format) {
    auto encoder = EncoderFactory().Create(env, format);
    return encoder ? std::make_unique<VideoRangeEncoder>(std::move(encoder)) : nullptr;
  }

  bool VideoToolboxEncoderAdapter::IsScalabilityModeSupported(webrtc::ScalabilityMode mode) {
    return mode == webrtc::ScalabilityMode::kL1T1;
  }

  std::vector<webrtc::SdpVideoFormat> VideoToolboxDecoderAdapter::SupportedFormats() {
    // the SDK lists only the profiles its encoder sends
    std::vector<webrtc::SdpVideoFormat> formats;
    for (const auto profile : {webrtc::H264Profile::kProfileConstrainedBaseline, webrtc::H264Profile::kProfileBaseline,
                               webrtc::H264Profile::kProfileMain, webrtc::H264Profile::kProfileConstrainedHigh,
                               webrtc::H264Profile::kProfileHigh}) {
      for (const auto *mode : {"1", "0"}) {
        formats.push_back(webrtc::CreateH264Format(profile, webrtc::H264Level::kLevel3_1, mode));
      }
    }
    return formats;
  }

  std::unique_ptr<webrtc::VideoDecoder>
  VideoToolboxDecoderAdapter::CreateDecoder(const webrtc::Environment &env, const webrtc::SdpVideoFormat &format) {
    auto decoder = DecoderFactory().Create(env, format);
    return decoder ? std::make_unique<VideoRangeDecoder>(std::move(decoder)) : nullptr;
  }

} // namespace python_webrtc
