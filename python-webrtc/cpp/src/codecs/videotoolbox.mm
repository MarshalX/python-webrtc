//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "videotoolbox.h"
#include "openh264.h"

#include <api/video/encoded_image.h>
#include <api/video/video_frame_buffer.h>
#include <api/video_codecs/h264_profile_level_id.h>
#include <api/video_codecs/video_decoder_software_fallback_wrapper.h>
#include <common_video/h264/h264_bitstream_parser.h>
#import <components/video_codec/RTCVideoDecoderFactoryH264.h>
#import <components/video_codec/nalu_rewriter.h>
#import <components/video_frame_buffer/RTCCVPixelBuffer.h>
#include <libyuv/convert.h>
#include <libyuv/convert_from.h>
#include <libyuv/planar_functions.h>
#include <media/base/media_constants.h>
#include <modules/video_coding/codecs/h264/include/h264.h>
#include <modules/video_coding/codecs/interface/common_constants.h>
#include <modules/video_coding/include/video_codec_interface.h>
#include <modules/video_coding/include/video_error_codes.h>
#include <native/api/video_decoder_factory.h>
#include <native/src/objc_frame_buffer.h>
#include <rtc_base/logging.h>

#include <CoreMedia/CoreMedia.h>
#include <CoreVideo/CoreVideo.h>
#include <TargetConditionals.h>
#include <VideoToolbox/VideoToolbox.h>

#include <algorithm>
#include <atomic>
#include <memory>

#include "../media/frame_buffer_pool.h"

// Encoding is our own VTCompressionSession; decoding is the SDK's, whose full-range output we map to video range.

namespace {

  // video range: luma in 16-235, chroma in 16-240
  constexpr unsigned kRangeOffset = 16;
  constexpr unsigned kLumaRange = 219;
  constexpr unsigned kChromaRange = 224;
  constexpr unsigned kFullRange = 255;
  constexpr unsigned kByteBits = 8;

  // libwebrtc's own H.264 QP thresholds, which its quality scaling applies over an encoder's by default
  constexpr int kLowQpThreshold = 24;
  constexpr int kHighQpThreshold = 37;

  // key frames come on request, so the periodic ones are rare
  constexpr int kMaxKeyFrameInterval = 7200;
  constexpr int kMaxKeyFrameIntervalSeconds = 240;

  constexpr int32_t kMicrosecondsPerSecond = 1'000'000;
  constexpr int kBitsPerKilobit = 1000;

  uint8_t *PlaneData(CVPixelBufferRef pixelBuffer, size_t plane) {
    return static_cast<uint8_t *>(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, plane));
  }

  int PlaneStride(CVPixelBufferRef pixelBuffer, size_t plane) {
    return static_cast<int>(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, plane));
  }

  // the CVPixelBuffer behind an SDK frame, or null
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

  // AutoLevel: the SDP's level 3.1 stops at 1280x720, VideoToolbox picks one that fits the stream
  CFStringRef ProfileLevelOf(const webrtc::SdpVideoFormat &format) {
    const auto id = webrtc::ParseSdpForH264ProfileLevelId(format.parameters);
    switch (id ? id->profile : webrtc::H264Profile::kProfileConstrainedBaseline) {
    case webrtc::H264Profile::kProfileConstrainedBaseline:
    case webrtc::H264Profile::kProfileBaseline:
      return kVTProfileLevel_H264_Baseline_AutoLevel;
    case webrtc::H264Profile::kProfileMain:
      return kVTProfileLevel_H264_Main_AutoLevel;
    default:
      return kVTProfileLevel_H264_High_AutoLevel;
    }
  }

  webrtc::H264PacketizationMode PacketizationModeOf(const webrtc::SdpVideoFormat &format) {
    const auto mode = format.parameters.find(static_cast<const char *>(webrtc::kH264FmtpPacketizationMode));
    const bool nonInterleaved = mode != format.parameters.end() && mode->second == "1";
    return nonInterleaved ? webrtc::H264PacketizationMode::NonInterleaved
                          : webrtc::H264PacketizationMode::SingleNalUnit;
  }

  bool IsKeyFrameRequested(const std::vector<webrtc::VideoFrameType> *types) {
    return types != nullptr && std::ranges::find(*types, webrtc::VideoFrameType::kVideoFrameKey) != types->end();
  }

  bool IsKeyFrame(CMSampleBufferRef sample) {
    CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(sample, /*createIfNecessary=*/0);
    if (attachments == nullptr || CFArrayGetCount(attachments) == 0) {
      return false;
    }
    const auto *const attachment = static_cast<CFDictionaryRef>(CFArrayGetValueAtIndex(attachments, 0));
    return CFDictionaryContainsKey(attachment, kCMSampleAttachmentKey_NotSync) == 0;
  }

  class VideoToolboxEncoder : public webrtc::VideoEncoder {
  public:
    explicit VideoToolboxEncoder(const webrtc::SdpVideoFormat &format)
        : _profileLevel(ProfileLevelOf(format)), _packetizationMode(PacketizationModeOf(format)) {}

    ~VideoToolboxEncoder() override { DestroySession(); }

    VideoToolboxEncoder(const VideoToolboxEncoder &) = delete;
    VideoToolboxEncoder &operator=(const VideoToolboxEncoder &) = delete;
    VideoToolboxEncoder(VideoToolboxEncoder &&) = delete;
    VideoToolboxEncoder &operator=(VideoToolboxEncoder &&) = delete;

    int InitEncode(const webrtc::VideoCodec *codec, const Settings & /*settings*/) override {
      DestroySession();
      _width = codec->width;
      _height = codec->height;
      _screenshare = codec->mode == webrtc::VideoCodecMode::kScreensharing;
      _bitrate = codec->startBitrate * kBitsPerKilobit;
      _framerate = codec->maxFramerate;
      return CreateSession() ? WEBRTC_VIDEO_CODEC_OK : WEBRTC_VIDEO_CODEC_ERROR;
    }

    int32_t RegisterEncodeCompleteCallback(webrtc::EncodedImageCallback *callback) override {
      _callback = callback;
      return WEBRTC_VIDEO_CODEC_OK;
    }

    int32_t Release() override {
      DestroySession();
      return WEBRTC_VIDEO_CODEC_OK;
    }

    int32_t Encode(const webrtc::VideoFrame &frame, const std::vector<webrtc::VideoFrameType> *types) override {
      @autoreleasepool {
        if (_session == nullptr || _callback.load() == nullptr) {
          return WEBRTC_VIDEO_CODEC_UNINITIALIZED;
        }
        // a frame failed after VideoToolbox took it: a new session starts with a key frame
        const bool restart = _failed.load();
        if (restart && !RestartSession()) {
          return WEBRTC_VIDEO_CODEC_FALLBACK_SOFTWARE;
        }
        const auto buffer = frame.video_frame_buffer();
        if (!FitSession(buffer->width(), buffer->height())) {
          return WEBRTC_VIDEO_CODEC_FALLBACK_SOFTWARE;
        }
        CVPixelBufferRef pixelBuffer = PoolBufferOf(*buffer);
        if (pixelBuffer == nullptr) {
          return WEBRTC_VIDEO_CODEC_ERROR;
        }

        NSDictionary *const options = restart || IsKeyFrameRequested(types)
                                          ? @{(__bridge NSString *)kVTEncodeFrameOptionKey_ForceKeyFrame : @YES}
                                          : nil;
        // freed by OnEncoded, which VideoToolbox calls for failed frames too
        auto *info = new FrameInfo{.rtpTimestamp = frame.rtp_timestamp(),
                                   .captureTimeMs = frame.render_time_ms(),
                                   .rotation = frame.rotation(),
                                   .width = _width,
                                   .height = _height};
        const OSStatus status = VTCompressionSessionEncodeFrame(
            _session, pixelBuffer, CMTimeMake(frame.timestamp_us(), kMicrosecondsPerSecond), kCMTimeInvalid,
            (__bridge CFDictionaryRef)options, info, nullptr);
        CVPixelBufferRelease(pixelBuffer);

        // lost on sleep, or the encoder failed: a new session starts with a key frame
        if (status == kVTInvalidSessionErr || status == kVTVideoEncoderMalfunctionErr) {
          RTC_LOG(LS_WARNING) << "VideoToolbox lost its H.264 session (" << status << "), starting a new one";
          DestroySession();
          return CreateSession() ? WEBRTC_VIDEO_CODEC_NO_OUTPUT : WEBRTC_VIDEO_CODEC_FALLBACK_SOFTWARE;
        }
        return status == noErr ? WEBRTC_VIDEO_CODEC_OK : WEBRTC_VIDEO_CODEC_ERROR;
      }
    }

    void SetRates(const RateControlParameters &parameters) override {
      _bitrate = parameters.bitrate.get_sum_bps();
      _framerate = parameters.framerate_fps;
      ApplyRates();
    }

    [[nodiscard]] EncoderInfo GetEncoderInfo() const override {
      EncoderInfo info;
      info.implementation_name = "VideoToolbox";
      info.is_hardware_accelerated = true;
      info.scaling_settings = ScalingSettings(kLowQpThreshold, kHighQpThreshold);
      // NV12 is what the session takes, copied as it is
      info.preferred_pixel_formats = {webrtc::VideoFrameBuffer::Type::kNV12, webrtc::VideoFrameBuffer::Type::kI420};
      return info;
    }

  private:
    // what OnEncoded needs of the frame
    struct FrameInfo {
      uint32_t rtpTimestamp;
      int64_t captureTimeMs;
      webrtc::VideoRotation rotation;
      int width;
      int height;
    };

    bool CreateSession() {
      @autoreleasepool {
#if TARGET_OS_OSX
        NSDictionary *const specification =
            @{(__bridge NSString *)kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder : @YES};
#else
        NSDictionary *const specification = @{};
#endif
        // the session's pool then hands out video-range NV12
        NSDictionary *const source = @{
          // NOLINTNEXTLINE(readability-redundant-parentheses): @() boxes the constant
          (__bridge NSString *)kCVPixelBufferPixelFormatTypeKey : @(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange),
          (__bridge NSString *)kCVPixelBufferWidthKey : @(_width),
          (__bridge NSString *)kCVPixelBufferHeightKey : @(_height),
          (__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey : @{},
        };
        _failed = false;
        _encoded = false;
        const OSStatus status = VTCompressionSessionCreate(
            nullptr, _width, _height, kCMVideoCodecType_H264, (__bridge CFDictionaryRef)specification,
            (__bridge CFDictionaryRef)source, nullptr, &OnEncoded, this, &_session);
        if (status != noErr) {
          RTC_LOG(LS_ERROR) << "VideoToolbox can't create an H.264 session: " << status;
          _session = nullptr;
          return false;
        }
        SetProperty(kVTCompressionPropertyKey_RealTime, @YES);
        SetProperty(kVTCompressionPropertyKey_ProfileLevel, (__bridge NSString *)_profileLevel);
        SetProperty(kVTCompressionPropertyKey_AllowFrameReordering, @NO);
        // NOLINTNEXTLINE(readability-redundant-parentheses): @() boxes the constant
        SetProperty(kVTCompressionPropertyKey_MaxKeyFrameInterval, @(kMaxKeyFrameInterval));
        // NOLINTNEXTLINE(readability-redundant-parentheses): @() boxes the constant
        SetProperty(kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration, @(kMaxKeyFrameIntervalSeconds));
        ApplyRates();
        return true;
      }
    }

    // waits for the frames in flight, so OnEncoded never runs after it
    void DestroySession() {
      if (_session != nullptr) {
        VTCompressionSessionCompleteFrames(_session, kCMTimeInvalid);
        VTCompressionSessionInvalidate(_session);
        CFRelease(_session);
        _session = nullptr;
      }
    }

    bool RestartSession() {
      DestroySession();
      if (!_encoded.load()) {
        RTC_LOG(LS_ERROR) << "VideoToolbox can't encode this H.264 stream";
        return false;
      }
      RTC_LOG(LS_WARNING) << "VideoToolbox starts a new H.264 session";
      return CreateSession();
    }

    // a session is made for one size
    bool FitSession(int width, int height) {
      if (width == _width && height == _height) {
        return true;
      }
      DestroySession();
      _width = width;
      _height = height;
      return CreateSession();
    }

    // no DataRateLimits: once they're set, VideoToolbox ignores any later rise of the bitrate
    void ApplyRates() {
      if (_session == nullptr) {
        return;
      }
      @autoreleasepool {
        if (_bitrate > 0) {
          SetProperty(kVTCompressionPropertyKey_AverageBitRate, @(_bitrate));
        }
        if (_framerate > 0) {
          SetProperty(kVTCompressionPropertyKey_ExpectedFrameRate, @(_framerate));
        }
      }
    }

    void SetProperty(CFStringRef key, id value) {
      const OSStatus status = VTSessionSetProperty(_session, key, (__bridge CFTypeRef)value);
      if (status != noErr) {
        RTC_LOG(LS_WARNING) << "VideoToolbox rejected " << [(__bridge NSString *)key UTF8String] << ": " << status;
      }
    }

    // the frame copied into a buffer of the session's pool, as NV12 without an I420 step; the caller releases it
    CVPixelBufferRef PoolBufferOf(webrtc::VideoFrameBuffer &buffer) {
      // the I420 of any other format, made before a pool buffer is taken
      webrtc::scoped_refptr<webrtc::I420BufferInterface> i420;
      if (buffer.type() != webrtc::VideoFrameBuffer::Type::kNV12) {
        i420 = buffer.ToI420();
        if (i420 == nullptr) {
          return nullptr;
        }
      }
      CVPixelBufferPoolRef pool = VTCompressionSessionGetPixelBufferPool(_session);
      CVPixelBufferRef pixelBuffer = nullptr;
      if (pool == nullptr || CVPixelBufferPoolCreatePixelBuffer(nullptr, pool, &pixelBuffer) != kCVReturnSuccess) {
        return nullptr;
      }
      if (CVPixelBufferLockBaseAddress(pixelBuffer, 0) != kCVReturnSuccess) {
        CVPixelBufferRelease(pixelBuffer);
        return nullptr;
      }
      if (i420 == nullptr) {
        const auto *nv12 = buffer.GetNV12();
        libyuv::NV12Copy(nv12->DataY(), nv12->StrideY(), nv12->DataUV(), nv12->StrideUV(), PlaneData(pixelBuffer, 0),
                         PlaneStride(pixelBuffer, 0), PlaneData(pixelBuffer, 1), PlaneStride(pixelBuffer, 1),
                         nv12->width(), nv12->height());
      } else {
        libyuv::I420ToNV12(i420->DataY(), i420->StrideY(), i420->DataU(), i420->StrideU(), i420->DataV(),
                           i420->StrideV(), PlaneData(pixelBuffer, 0), PlaneStride(pixelBuffer, 0),
                           PlaneData(pixelBuffer, 1), PlaneStride(pixelBuffer, 1), i420->width(), i420->height());
      }
      CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
      CVBufferSetAttachment(pixelBuffer, kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_601_4,
                            kCVAttachmentMode_ShouldPropagate);
      return pixelBuffer;
    }

    // on VideoToolbox's thread, one frame at a time
    static void OnEncoded(void *encoder, void *info, OSStatus status, VTEncodeInfoFlags flags,
                          CMSampleBufferRef sample) {
      static_cast<VideoToolboxEncoder *>(encoder)->Deliver(std::unique_ptr<FrameInfo>(static_cast<FrameInfo *>(info)),
                                                           status, flags, sample);
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): mirrors VTCompressionOutputCallback
    void Deliver(std::unique_ptr<FrameInfo> info, OSStatus status, VTEncodeInfoFlags flags, CMSampleBufferRef sample) {
      if (status != noErr) {
        RTC_LOG(LS_ERROR) << "VideoToolbox failed to encode an H.264 frame: " << status;
        _failed = true;
        return;
      }
      auto *callback = _callback.load();
      if (callback == nullptr || sample == nullptr || (flags & kVTEncodeInfo_FrameDropped) != 0) {
        return;
      }
      const bool key = IsKeyFrame(sample);
      webrtc::Buffer annexB;
      if (!webrtc::H264CMSampleBufferToAnnexBBuffer(sample, key, &annexB)) {
        return;
      }
      _qpParser.ParseBitstream(annexB);

      webrtc::EncodedImage image;
      image._encodedWidth = info->width;
      image._encodedHeight = info->height;
      image._frameType = key ? webrtc::VideoFrameType::kVideoFrameKey : webrtc::VideoFrameType::kVideoFrameDelta;
      image.SetRtpTimestamp(info->rtpTimestamp);
      image.capture_time_ms_ = info->captureTimeMs;
      image.rotation_ = info->rotation;
      image.content_type_ =
          _screenshare ? webrtc::VideoContentType::SCREENSHARE : webrtc::VideoContentType::UNSPECIFIED;
      image.qp_ = _qpParser.GetLastSliceQp().value_or(-1);
      image.SetEncodedData(webrtc::EncodedImageBuffer::Create(std::move(annexB)));

      webrtc::CodecSpecificInfo codecInfo;
      codecInfo.codecType = webrtc::kVideoCodecH264;
      // NOLINTBEGIN(cppcoreguidelines-pro-type-union-access): libwebrtc's CodecSpecificInfo is a union
      codecInfo.codecSpecific.H264.packetization_mode = _packetizationMode;
      codecInfo.codecSpecific.H264.temporal_idx = webrtc::kNoTemporalIdx;
      codecInfo.codecSpecific.H264.idr_frame = key;
      // NOLINTEND(cppcoreguidelines-pro-type-union-access)
      callback->OnEncodedImage(image, &codecInfo);
      _encoded = true;
    }

    const CFStringRef _profileLevel;
    const webrtc::H264PacketizationMode _packetizationMode;
    // set on the encoding thread, read on VideoToolbox's
    std::atomic<webrtc::EncodedImageCallback *> _callback = nullptr;
    VTCompressionSessionRef _session = nullptr;
    int _width = 0;
    int _height = 0;
    bool _screenshare = false;
    uint32_t _bitrate = 0;
    double _framerate = 0;
    // of the current session, set on VideoToolbox's thread
    std::atomic<bool> _failed = false;
    std::atomic<bool> _encoded = false;
    // VideoToolbox's thread only
    webrtc::H264BitstreamParser _qpParser;
  };

  // the SDK's decoder, with its full-range output mapped to video range
  class VideoRangeDecoder : public webrtc::VideoDecoder, public webrtc::DecodedImageCallback {
  public:
    explicit VideoRangeDecoder(std::unique_ptr<webrtc::VideoDecoder> decoder) : _decoder(std::move(decoder)) {}

    bool Configure(const Settings &settings) override {
      _pool.Resize(settings.buffer_pool_size());
      return _decoder->Configure(settings);
    }

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
    // full-range NV12 to video-range I420; false drops the frame
    bool Convert(webrtc::VideoFrame &frame) {
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
      const uint8_t *luma = PlaneData(pixelBuffer, 0);
      const uint8_t *chroma = PlaneData(pixelBuffer, 1);
      if (luma == nullptr || chroma == nullptr) {
        CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
        return false;
      }
      auto i420 = _pool.CreateI420(width, height);
      ToVideoRange(luma, PlaneStride(pixelBuffer, 0), chroma, PlaneStride(pixelBuffer, 1), *i420);
      CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
      frame.set_video_frame_buffer(i420);
      return true;
    }

    // 0-255 onto 16-(16 + range), rounded; arithmetic rather than a table, so it vectorizes
    static uint8_t Compressed(unsigned value, unsigned range) {
      // v / 255 as (v + 1 + (v >> 8)) >> 8, exact below 65280: 16-bit lanes, twice as many as 32-bit ones
      const auto scaled = static_cast<uint16_t>((value * range) + (kFullRange / 2));
      return static_cast<uint8_t>(kRangeOffset +
                                  static_cast<uint16_t>((scaled + 1 + (scaled >> kByteBits)) >> kByteBits));
    }

    // NV12 into I420 and onto video range in one pass over each row
    static void ToVideoRange(const uint8_t *y, int strideY, const uint8_t *uv, int strideUV, webrtc::I420Buffer &i420) {
      // the buffer's getters are virtual: read once, so the loops vectorize
      const ptrdiff_t width = i420.width();
      const ptrdiff_t height = i420.height();
      const ptrdiff_t chromaWidth = i420.ChromaWidth();
      const ptrdiff_t chromaHeight = i420.ChromaHeight();
      uint8_t *toY = i420.MutableDataY();
      uint8_t *toU = i420.MutableDataU();
      uint8_t *toV = i420.MutableDataV();
      const ptrdiff_t strideToY = i420.StrideY();
      const ptrdiff_t strideToU = i420.StrideU();
      const ptrdiff_t strideToV = i420.StrideV();
      for (ptrdiff_t row = 0; row < height; ++row) {
        const uint8_t *from = y + (row * strideY);
        uint8_t *line = toY + (row * strideToY);
        for (ptrdiff_t column = 0; column < width; ++column) {
          line[column] = Compressed(from[column], kLumaRange);
        }
      }
      for (ptrdiff_t row = 0; row < chromaHeight; ++row) {
        const uint8_t *from = uv + (row * strideUV);
        uint8_t *u = toU + (row * strideToU);
        uint8_t *v = toV + (row * strideToV);
        for (ptrdiff_t column = 0; column < chromaWidth; ++column) {
          u[column] = Compressed(from[2 * column], kChromaRange);
          v[column] = Compressed(from[(2 * column) + 1], kChromaRange);
        }
      }
    }

    std::unique_ptr<webrtc::VideoDecoder> _decoder;
    // set on the decoding thread, called on VideoToolbox's
    std::atomic<webrtc::DecodedImageCallback *> _callback = nullptr;
    // the converted frames, made on VideoToolbox's thread
    python_webrtc::FrameBufferPool _pool;
  };

  // leaked: decoders may outlive static destruction at interpreter exit
  webrtc::VideoDecoderFactory &DecoderFactory() {
    static auto *factory =
        webrtc::ObjCToNativeVideoDecoderFactory([[RTC_OBJC_TYPE(RTCVideoDecoderFactoryH264) alloc] init]).release();
    return *factory;
  }

} // namespace

namespace python_webrtc {

  std::vector<webrtc::SdpVideoFormat> VideoToolboxEncoderAdapter::SupportedFormats() {
    // level 3.1 like browsers; the stream's own level follows its size
    return {
        webrtc::CreateH264Format(webrtc::H264Profile::kProfileConstrainedHigh, webrtc::H264Level::kLevel3_1, "1"),
        // the same stream, as frames are never reordered: for Chrome, which offers no Constrained High
        webrtc::CreateH264Format(webrtc::H264Profile::kProfileHigh, webrtc::H264Level::kLevel3_1, "1"),
        webrtc::CreateH264Format(webrtc::H264Profile::kProfileConstrainedBaseline, webrtc::H264Level::kLevel3_1, "1")};
  }

  std::unique_ptr<webrtc::VideoEncoder>
  VideoToolboxEncoderAdapter::CreateEncoder(const webrtc::Environment & /*env*/, const webrtc::SdpVideoFormat &format) {
    return std::make_unique<VideoToolboxEncoder>(format);
  }

  bool VideoToolboxEncoderAdapter::IsScalabilityModeSupported(webrtc::ScalabilityMode mode) {
    return mode == webrtc::ScalabilityMode::kL1T1;
  }

  std::vector<webrtc::SdpVideoFormat> VideoToolboxDecoderAdapter::SupportedFormats() {
    // the SDK's factory lists only CB and CH, VideoToolbox decodes all of these
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
    if (decoder == nullptr) {
      return nullptr;
    }
    std::unique_ptr<webrtc::VideoDecoder> videoToolbox = std::make_unique<VideoRangeDecoder>(std::move(decoder));
    auto fallback = OpenH264::Enabled() ? OpenH264DecoderAdapter::CreateDecoder(env, format) : nullptr;
    if (fallback == nullptr) {
      return videoToolbox;
    }
    return webrtc::CreateVideoDecoderSoftwareFallbackWrapper(env, std::move(fallback), std::move(videoToolbox));
  }

} // namespace python_webrtc
