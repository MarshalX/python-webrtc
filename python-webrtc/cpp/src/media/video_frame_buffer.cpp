//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "video_frame_buffer.h"

#include <cstring>
#include <stdexcept>

#include <api/video/i420_buffer.h>
#include <api/video/nv12_buffer.h>
#include <common_video/include/video_frame_buffer.h>
#include <libyuv/convert.h>
#include <libyuv/convert_argb.h>
#include <libyuv/convert_from_argb.h>
#include <libyuv/planar_functions.h>

#include <pybind11/stl.h>

namespace python_webrtc {

  namespace {

    using Layout = PixelFormat::Layout;

    const PixelFormat FORMATS[] = {
        {"I420", Layout::I420, 8, false, false},     {"I420P10", Layout::I420, 10, false, false},
        {"I420P12", Layout::I420, 12, false, false}, {"I420A", Layout::I420, 8, true, false},
        {"I420AP10", Layout::I420, 10, true, false}, {"I420AP12", Layout::I420, 12, true, false},
        {"I422", Layout::I422, 8, false, false},     {"I422P10", Layout::I422, 10, false, false},
        {"I422P12", Layout::I422, 12, false, false}, {"I422A", Layout::I422, 8, true, false},
        {"I422AP10", Layout::I422, 10, true, false}, {"I422AP12", Layout::I422, 12, true, false},
        {"I444", Layout::I444, 8, false, false},     {"I444P10", Layout::I444, 10, false, false},
        {"I444P12", Layout::I444, 12, false, false}, {"I444A", Layout::I444, 8, true, false},
        {"I444AP10", Layout::I444, 10, true, false}, {"I444AP12", Layout::I444, 12, true, false},
        {"NV12", Layout::NV12, 8, false, false},     {"RGBA", Layout::RGB, 8, true, true},
        {"RGBX", Layout::RGB, 8, false, true},       {"BGRA", Layout::RGB, 8, true, false},
        {"BGRX", Layout::RGB, 8, false, false},
    };

    int Divide(int value, int divisor) {
      return (value + divisor - 1) / divisor;
    }

  } // namespace

  void VideoFrameBuffer::Init(pybind11::module &m) {
    pybind11::class_<VideoFrameBuffer, std::shared_ptr<VideoFrameBuffer>>(m, "VideoFrameBuffer")
        .def_static("fromData", &VideoFrameBuffer::FromData, pybind11::arg("format"), pybind11::arg("width"),
                    pybind11::arg("height"), pybind11::arg("data"), pybind11::arg("layout"))
        .def_property_readonly("format", &VideoFrameBuffer::GetFormat)
        .def_property_readonly("width", &VideoFrameBuffer::width)
        .def_property_readonly("height", &VideoFrameBuffer::height)
        .def("withoutAlpha", &VideoFrameBuffer::WithoutAlpha)
        .def("copyPlanes", &VideoFrameBuffer::CopyPlanes, pybind11::arg("destination"), pybind11::arg("planes"))
        .def("convertTo", &VideoFrameBuffer::ConvertTo, pybind11::arg("destination"), pybind11::arg("format"),
             pybind11::arg("x"), pybind11::arg("y"), pybind11::arg("width"), pybind11::arg("height"),
             pybind11::arg("offset"), pybind11::arg("stride"), pybind11::arg("matrix"), pybind11::arg("fullRange"));
  }

  const PixelFormat &PixelFormat::Parse(const std::string &name) {
    for (const auto &format: FORMATS) {
      if (name == format.name) {
        return format;
      }
    }
    throw pybind11::value_error("Unsupported pixel format " + name);
  }

  std::vector<PixelFormat::Plane> PixelFormat::Planes() const {
    switch (layout) {
      case Layout::NV12:
        return {{1, 1, 1}, {2, 2, 2}};
      case Layout::RGB:
        return {{4, 1, 1}};
      default: {
        int bytes = bits > 8 ? 2 : 1;
        int x = layout == Layout::I444 ? 1 : 2;
        int y = layout == Layout::I420 ? 2 : 1;
        std::vector<Plane> planes = {{bytes, 1, 1}, {bytes, x, y}, {bytes, x, y}};
        if (alpha) {
          planes.push_back({bytes, 1, 1});
        }
        return planes;
      }
    }
  }

  int PixelFormat::Plane::Columns(int width) const {
    return Divide(width, subsamplingX);
  }

  int PixelFormat::Plane::Rows(int height) const {
    return Divide(height, subsamplingY);
  }

  std::shared_ptr<VideoFrameBuffer> VideoFrameBuffer::FromWebrtc(
      webrtc::scoped_refptr<webrtc::VideoFrameBuffer> buffer) {
    using Type = webrtc::VideoFrameBuffer::Type;
    std::shared_ptr<VideoFrameBuffer> result;
    auto wrapYuv = [&](const char *name, const webrtc::PlanarYuv8Buffer *planes) {
      result.reset(new VideoFrameBuffer(PixelFormat::Parse(name), buffer->width(), buffer->height()));
      result->_data = {planes->DataY(), planes->DataU(), planes->DataV(), nullptr};
      result->_stride = {planes->StrideY(), planes->StrideU(), planes->StrideV(), 0};
    };
    switch (buffer->type()) {
      case Type::kI420A: {
        auto planes = buffer->GetI420A();
        wrapYuv("I420A", planes);
        result->_data[3] = planes->DataA();
        result->_stride[3] = planes->StrideA();
        break;
      }
      case Type::kI422:
        wrapYuv("I422", buffer->GetI422());
        break;
      case Type::kI444:
        wrapYuv("I444", buffer->GetI444());
        break;
      case Type::kNV12: {
        auto planes = buffer->GetNV12();
        result.reset(new VideoFrameBuffer(PixelFormat::Parse("NV12"), buffer->width(), buffer->height()));
        result->_data = {planes->DataY(), planes->DataUV(), nullptr, nullptr};
        result->_stride = {planes->StrideY(), planes->StrideUV(), 0, 0};
        break;
      }
      default:
        if (buffer->type() != Type::kI420) {
          // native or high bit depth
          buffer = buffer->ToI420();
          if (!buffer) {
            throw std::runtime_error("The frame can't be converted to I420");
          }
        }
        wrapYuv("I420", buffer->GetI420());
        break;
    }
    result->_webrtc = std::move(buffer);
    return result;
  }

  std::shared_ptr<VideoFrameBuffer> VideoFrameBuffer::FromData(const std::string &formatName, int width, int height,
                                                               const pybind11::buffer &data,
                                                               const std::vector<SourceLayout> &layout) {
    const auto &format = PixelFormat::Parse(formatName);
    auto planes = format.Planes();
    if (width <= 0 || height <= 0) {
      throw pybind11::value_error("The frame must have a positive size");
    }
    if (layout.size() != planes.size()) {
      throw pybind11::value_error("The layout must have one entry per plane");
    }

    auto info = data.request();
    auto source = static_cast<const uint8_t *>(info.ptr);
    auto sourceSize = static_cast<size_t>(info.size * info.itemsize);

    std::shared_ptr<VideoFrameBuffer> result(new VideoFrameBuffer(format, width, height));
    std::array<size_t, 4> offsets{};
    std::array<size_t, 4> rows{};
    size_t total = 0;
    for (size_t i = 0; i < planes.size(); ++i) {
      offsets[i] = total;
      result->_stride[i] = planes[i].Columns(width) * planes[i].sampleBytes;
      rows[i] = planes[i].Rows(height);
      auto [offset, stride] = layout[i];
      if (stride < static_cast<size_t>(result->_stride[i]) ||
          offset + stride * (rows[i] - 1) + result->_stride[i] > sourceSize) {
        throw pybind11::value_error("The layout doesn't fit in the data");
      }
      total += static_cast<size_t>(result->_stride[i]) * rows[i];
    }
    result->_owned = std::make_shared<std::vector<uint8_t>>(total);

    {
      pybind11::gil_scoped_release release;
      for (size_t i = 0; i < planes.size(); ++i) {
        auto [offset, stride] = layout[i];
        size_t rowBytes = result->_stride[i];
        for (size_t row = 0; row < rows[i]; ++row) {
          std::memcpy(result->_owned->data() + offsets[i] + row * rowBytes, source + offset + row * stride, rowBytes);
        }
      }
    }
    for (size_t i = 0; i < planes.size(); ++i) {
      result->_data[i] = result->_owned->data() + offsets[i];
    }
    return result;
  }

  std::shared_ptr<VideoFrameBuffer> VideoFrameBuffer::WithoutAlpha() const {
    if (!_format->alpha) {
      throw pybind11::value_error("The frame has no alpha");
    }
    std::string name = _format->name;
    if (_format->layout == Layout::RGB) {
      name[3] = 'X';
    } else {
      // I420A, I420AP10...
      name.erase(4, 1);
    }
    std::shared_ptr<VideoFrameBuffer> result(new VideoFrameBuffer(*this));
    result->_format = &PixelFormat::Parse(name);
    if (_format->layout != Layout::RGB) {
      result->_data[3] = nullptr;
      result->_stride[3] = 0;
    }
    return result;
  }

  void VideoFrameBuffer::CopyPlanes(const pybind11::buffer &destination, const std::vector<PlaneCopy> &copies) const {
    auto info = destination.request(true);
    auto size = static_cast<size_t>(info.size * info.itemsize);
    auto target = static_cast<uint8_t *>(info.ptr);
    auto planes = _format->Planes();
    if (copies.size() != planes.size()) {
      throw pybind11::value_error("One copy per plane is needed");
    }
    for (size_t i = 0; i < planes.size(); ++i) {
      auto [leftBytes, top, rowBytes, rows, offset, stride] = copies[i];
      size_t planeRows = planes[i].Rows(_height);
      size_t planeRowBytes = static_cast<size_t>(planes[i].Columns(_width)) * planes[i].sampleBytes;
      if (rows > 0 && rowBytes > 0 &&
          (top + rows > planeRows || leftBytes + rowBytes > planeRowBytes || stride < rowBytes ||
           offset + stride * (rows - 1) + rowBytes > size)) {
        throw pybind11::value_error("The copy is out of the bounds of the frame or of the destination");
      }
    }

    pybind11::gil_scoped_release release;
    for (size_t i = 0; i < planes.size(); ++i) {
      auto [leftBytes, top, rowBytes, rows, offset, stride] = copies[i];
      for (size_t row = 0; row < rows && rowBytes > 0; ++row) {
        std::memcpy(target + offset + row * stride, _data[i] + (top + row) * _stride[i] + leftBytes, rowBytes);
      }
    }
  }

  VideoFrameBuffer::EightBit VideoFrameBuffer::ToEightBit() const {
    EightBit result;
    if (_format->bits == 8) {
      result.data = _data;
      result.stride = _stride;
      return result;
    }
    auto planes = _format->Planes();
    std::array<size_t, 4> offsets{};
    size_t total = 0;
    for (size_t i = 0; i < planes.size(); ++i) {
      offsets[i] = total;
      result.stride[i] = planes[i].Columns(_width);
      total += static_cast<size_t>(result.stride[i]) * planes[i].Rows(_height);
    }
    result.storage.resize(total);
    // the samples are in the low bits of 16: scaled down to 8 (x * scale >> 16)
    int scale = 1 << (24 - _format->bits);
    for (size_t i = 0; i < planes.size(); ++i) {
      auto target = result.storage.data() + offsets[i];
      libyuv::Convert16To8Plane(reinterpret_cast<const uint16_t *>(_data[i]), _stride[i] / 2, target,
                                result.stride[i], scale, result.stride[i], planes[i].Rows(_height));
      result.data[i] = target;
    }
    return result;
  }

  void VideoFrameBuffer::ConvertTo(const pybind11::buffer &destination, const std::string &formatName, int x, int y,
                                   int width, int height, size_t offset, size_t stride, const std::string &matrix,
                                   bool fullRange) const {
    const auto &format = PixelFormat::Parse(formatName);
    if (format.layout != Layout::RGB) {
      throw pybind11::value_error("Frames are converted to RGB formats only");
    }
    if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > _width || y + height > _height) {
      throw pybind11::value_error("The rect is out of the bounds of the frame");
    }
    auto info = destination.request(true);
    auto size = static_cast<size_t>(info.size * info.itemsize);
    if (stride < static_cast<size_t>(width) * 4 || offset + stride * (height - 1) + width * 4 > size) {
      throw pybind11::value_error("The destination is too small");
    }
    auto dst = static_cast<uint8_t *>(info.ptr) + offset;
    auto dstStride = static_cast<int>(stride);
    bool rgbOrder = format.rgbOrder;
    // alpha is kept when both the frame and the format have it, opaque otherwise
    bool alpha = format.alpha && _format->alpha;

    // the YUV matrix of the frame: U and V swapped (Yvu) give R and B swapped
    const libyuv::YuvConstants *yuv = fullRange ? &libyuv::kYuvJPEGConstants : &libyuv::kYuvI601Constants;
    const libyuv::YuvConstants *yvu = fullRange ? &libyuv::kYvuJPEGConstants : &libyuv::kYvuI601Constants;
    if (matrix == "bt709") {
      yuv = fullRange ? &libyuv::kYuvF709Constants : &libyuv::kYuvH709Constants;
      yvu = fullRange ? &libyuv::kYvuF709Constants : &libyuv::kYvuH709Constants;
    } else if (matrix == "bt2020-ncl") {
      yuv = fullRange ? &libyuv::kYuvV2020Constants : &libyuv::kYuv2020Constants;
      yvu = fullRange ? &libyuv::kYvuV2020Constants : &libyuv::kYvu2020Constants;
    }
    auto constants = rgbOrder ? yvu : yuv;

    pybind11::gil_scoped_release release;
    auto planes = _format->Planes();
    auto source = ToEightBit();
    auto plane = [&](int i) {
      // high bit depth planes are 8-bit now
      int sampleBytes = _format->bits == 8 ? planes[i].sampleBytes : 1;
      return source.data[i] + (y / planes[i].subsamplingY) * source.stride[i] +
             (x / planes[i].subsamplingX) * sampleBytes;
    };
    // libyuv writes B, G, R, A (its ARGB): swapping U and V swaps R and B
    int u = rgbOrder ? 2 : 1;
    int v = rgbOrder ? 1 : 2;

    int result = 0;
    switch (_format->layout) {
      case Layout::I420:
      case Layout::I422:
      case Layout::I444: {
        bool i420 = _format->layout == Layout::I420;
        bool i422 = _format->layout == Layout::I422;
        if (alpha) {
          auto convert = i420   ? libyuv::I420AlphaToARGBMatrix
                         : i422 ? libyuv::I422AlphaToARGBMatrix
                                : libyuv::I444AlphaToARGBMatrix;
          result = convert(plane(0), source.stride[0], plane(u), source.stride[u], plane(v), source.stride[v],
                           plane(3), source.stride[3], dst, dstStride, constants, width, height, 0);
        } else {
          auto convert = i420 ? libyuv::I420ToARGBMatrix : i422 ? libyuv::I422ToARGBMatrix : libyuv::I444ToARGBMatrix;
          result = convert(plane(0), source.stride[0], plane(u), source.stride[u], plane(v), source.stride[v], dst,
                           dstStride, constants, width, height);
        }
        break;
      }
      case Layout::NV12: {
        // NV21 is NV12 with U and V swapped
        auto convert = rgbOrder ? libyuv::NV21ToARGBMatrix : libyuv::NV12ToARGBMatrix;
        result = convert(plane(0), source.stride[0], plane(1), source.stride[1], dst, dstStride, constants, width,
                         height);
        break;
      }
      case Layout::RGB:
        if (_format->rgbOrder == rgbOrder) {
          result = libyuv::ARGBCopy(plane(0), source.stride[0], dst, dstStride, width, height);
        } else {
          // swapping R and B is its own inverse
          result = libyuv::ARGBToABGR(plane(0), source.stride[0], dst, dstStride, width, height);
        }
        break;
    }
    if (result != 0) {
      throw std::runtime_error("The frame can't be converted");
    }
    if (!alpha) {
      // opaque, like a conversion from YUV without alpha
      for (int row = 0; row < height; ++row) {
        auto pixel = dst + row * stride + 3;
        for (int column = 0; column < width; ++column, pixel += 4) {
          *pixel = 255;
        }
      }
    }
  }

  webrtc::scoped_refptr<webrtc::VideoFrameBuffer> VideoFrameBuffer::ToWebrtc() const {
    const auto &format = *_format;
    // a received I420A buffer without its alpha is wrapped again as I420
    bool alphaDropped = !format.alpha && _webrtc && _webrtc->type() == webrtc::VideoFrameBuffer::Type::kI420A;
    if (_webrtc && !alphaDropped) {
      return _webrtc;
    }
    // the planes live as long as the libwebrtc buffer wrapping them
    auto keep = [owned = _owned, webrtc = _webrtc]() {};
    if (format.layout == Layout::NV12) {
      auto buffer = webrtc::NV12Buffer::Create(_width, _height);
      libyuv::CopyPlane(_data[0], _stride[0], buffer->MutableDataY(), buffer->StrideY(), _width, _height);
      auto uv = format.Planes()[1];
      libyuv::CopyPlane(_data[1], _stride[1], buffer->MutableDataUV(), buffer->StrideUV(),
                        uv.Columns(_width) * uv.sampleBytes, uv.Rows(_height));
      return buffer;
    }
    if (format.layout == Layout::RGB) {
      auto buffer = webrtc::I420Buffer::Create(_width, _height);
      auto convert = format.rgbOrder ? libyuv::ABGRToI420 : libyuv::ARGBToI420;
      convert(_data[0], _stride[0], buffer->MutableDataY(), buffer->StrideY(), buffer->MutableDataU(),
              buffer->StrideU(), buffer->MutableDataV(), buffer->StrideV(), _width, _height);
      return buffer;
    }
    if (format.bits == 8) {
      switch (format.layout) {
        case Layout::I420:
          if (format.alpha) {
            return webrtc::WrapI420ABuffer(_width, _height, _data[0], _stride[0], _data[1], _stride[1], _data[2],
                                           _stride[2], _data[3], _stride[3], keep);
          }
          return webrtc::WrapI420Buffer(_width, _height, _data[0], _stride[0], _data[1], _stride[1], _data[2],
                                        _stride[2], keep);
        case Layout::I422:
          if (!format.alpha) {
            return webrtc::WrapI422Buffer(_width, _height, _data[0], _stride[0], _data[1], _stride[1], _data[2],
                                          _stride[2], keep);
          }
          break;
        default:
          if (!format.alpha) {
            return webrtc::WrapI444Buffer(_width, _height, _data[0], _stride[0], _data[1], _stride[1], _data[2],
                                          _stride[2], keep);
          }
          break;
      }
    }
    // high bit depth, or alpha libwebrtc has no buffer for: 8-bit I420 without alpha
    auto buffer = webrtc::I420Buffer::Create(_width, _height);
    auto source = ToEightBit();
    auto convert = format.layout == Layout::I420   ? libyuv::I420Copy
                   : format.layout == Layout::I422 ? libyuv::I422ToI420
                                                   : libyuv::I444ToI420;
    convert(source.data[0], source.stride[0], source.data[1], source.stride[1], source.data[2], source.stride[2],
            buffer->MutableDataY(), buffer->StrideY(), buffer->MutableDataU(), buffer->StrideU(),
            buffer->MutableDataV(), buffer->StrideV(), _width, _height);
    return buffer;
  }

} // namespace python_webrtc
