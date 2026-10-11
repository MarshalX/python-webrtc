//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_VIDEO_FRAME_BUFFER_H_
#define PYTHON_WEBRTC_MEDIA_VIDEO_FRAME_BUFFER_H_

#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <tuple>
#include <vector>

#include <api/scoped_refptr.h>
#include <api/video/video_frame_buffer.h>

#include <pybind11/pybind11.h>

#include "../utils/native_object.h"

namespace python_webrtc {

  // A pixel format of VideoFrame (WebCodecs VideoPixelFormat)
  struct PixelFormat {
    enum class Layout : uint8_t { I420, I422, I444, NV12, RGB };

    const char *name;
    Layout layout;
    int bits;
    bool alpha;
    // R, G, B in memory, rather than B, G, R (RGB layout only)
    bool rgbOrder;

    struct Plane {
      int sampleBytes;
      int subsamplingX;
      int subsamplingY;

      // samples in a row of the plane of a frame this wide
      [[nodiscard]] int Columns(int width) const;

      [[nodiscard]] int Rows(int height) const;
    };

    [[nodiscard]] std::vector<Plane> Planes() const;

    static const PixelFormat &Parse(const std::string &name);
  };

  // The planes of a VideoFrame, kept by reference from libwebrtc or copied from Python; immutable, so clones share it
  class VideoFrameBuffer : public NativeObject<VideoFrameBuffer> {
  public:
    static constexpr const char *kName = "VideoFrameBuffer";

    // (offset, stride) of a plane in the data of the application
    using SourceLayout = std::tuple<size_t, size_t>;
    // (leftBytes, top, rowBytes, rows, destinationOffset, destinationStride) of a plane to copy
    using PlaneCopy = std::tuple<size_t, size_t, size_t, size_t, size_t, size_t>;

    static void Init(pybind11::module &m);

    // a frame buffer libwebrtc delivered, converted to I420 if it's in a format VideoFrame doesn't have
    static std::shared_ptr<VideoFrameBuffer> FromWebrtc(webrtc::scoped_refptr<webrtc::VideoFrameBuffer> buffer);

    // copies the planes of the data at their layout into a buffer of its own
    static std::shared_ptr<VideoFrameBuffer> FromData(const std::string &format, int width, int height,
                                                      const pybind11::buffer &data,
                                                      const std::vector<SourceLayout> &layout);

    [[nodiscard]] std::string GetFormat() const { return _format->name; }

    [[nodiscard]] int width() const { return _width; }

    [[nodiscard]] int height() const { return _height; }

    // the same planes without the alpha one (I420A to I420, RGBA to RGBX...)
    [[nodiscard]] std::shared_ptr<VideoFrameBuffer> WithoutAlpha() const;

    // copies rows of the planes into the destination, at the given place of each
    void CopyPlanes(const pybind11::buffer &destination, const std::vector<PlaneCopy> &copies) const;

    // converts a rect into an RGB format, with the YUV matrix (VideoMatrixCoefficients) and range of the frame
    void ConvertTo(const pybind11::buffer &destination, const std::string &format, int x, int y, int width, int height,
                   size_t offset, size_t stride, const std::string &matrix, bool fullRange) const;

    // the frame as libwebrtc takes it: its planes when they're in a format libwebrtc has, converted to I420 if not
    [[nodiscard]] webrtc::scoped_refptr<webrtc::VideoFrameBuffer> ToWebrtc() const;

  private:
    friend class NativeObject<VideoFrameBuffer>;

    VideoFrameBuffer(const PixelFormat &format, int width, int height)
        : _format(&format), _width(width), _height(height) {}

    VideoFrameBuffer(const VideoFrameBuffer &other, const PixelFormat &format)
        : _format(&format), _width(other._width), _height(other._height), _data(other._data), _stride(other._stride),
          _webrtc(other._webrtc), _owned(other._owned) {}

    // The planes with 8 bits per sample: the planes themselves, or a copy of them shifted down
    struct EightBit {
      std::array<const uint8_t *, 4> data{};
      std::array<int, 4> stride{};
      std::vector<uint8_t> storage;
    };

    [[nodiscard]] EightBit ToEightBit() const;

    const PixelFormat *_format;
    int _width;
    int _height;
    std::array<const uint8_t *, 4> _data{};
    // in bytes
    std::array<int, 4> _stride{};
    // what the planes point into
    webrtc::scoped_refptr<webrtc::VideoFrameBuffer> _webrtc;
    std::shared_ptr<std::vector<uint8_t>> _owned;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_VIDEO_FRAME_BUFFER_H_
