//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "audio_samples.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string_view>

#include "utils/buffer.h"
#include "utils/gil.h"

namespace python_webrtc {

  namespace {

    enum class SampleType : uint8_t { U8, S16, S32, F32 };

    struct SampleFormat {
      SampleType type;
      bool planar;
    };

    constexpr std::string_view kPlanarSuffix = "-planar";
    constexpr double kS16Scale = 32768.0;
    constexpr double kS32Scale = 2147483648.0;
    // unsigned 8-bit samples are offset by half their range
    constexpr int kU8Offset = 128;
    constexpr double kU8Scale = 128.0;
    // how far each type sits below s32
    constexpr int kU8Shift = 24;
    constexpr int kS16Shift = 16;

    SampleFormat ParseFormat(const std::string &format) {
      std::string_view type = format;
      const bool planar =
          type.size() > kPlanarSuffix.size() && type.substr(type.size() - kPlanarSuffix.size()) == kPlanarSuffix;
      if (planar) {
        type.remove_suffix(kPlanarSuffix.size());
      }
      if (type == "u8") {
        return {.type = SampleType::U8, .planar = planar};
      }
      if (type == "s16") {
        return {.type = SampleType::S16, .planar = planar};
      }
      if (type == "s32") {
        return {.type = SampleType::S32, .planar = planar};
      }
      if (type == "f32") {
        return {.type = SampleType::F32, .planar = planar};
      }
      throw pybind11::value_error("Unsupported sample format " + format);
    }

    size_t Size(SampleType type) {
      switch (type) {
      case SampleType::U8:
        return sizeof(uint8_t);
      case SampleType::S16:
        return sizeof(int16_t);
      default:
        return sizeof(int32_t);
      }
    }

    // unaligned, as the buffers of Python may be
    template <typename T>
    T Load(const uint8_t *data) {
      T value;
      std::memcpy(&value, data, sizeof(T));
      return value;
    }

    template <typename T>
    void Store(uint8_t *data, T value) {
      std::memcpy(data, &value, sizeof(T));
    }

    // the sample as s32, the widest type, so integer conversions are exact shifts
    int32_t ReadInt(const uint8_t *data, SampleType type) {
      switch (type) {
      case SampleType::U8:
        return static_cast<int32_t>(static_cast<uint32_t>(*data - kU8Offset) << kU8Shift);
      case SampleType::S16:
        return static_cast<int32_t>(static_cast<uint32_t>(Load<int16_t>(data)) << kS16Shift);
      case SampleType::S32:
        return Load<int32_t>(data);
      default: {
        const double sample = Load<float>(data);
        // NaN is silence: clamping keeps it, and converting it to an integer is undefined
        if (std::isnan(sample)) {
          return 0;
        }
        const double scaled = std::clamp(sample, -1.0, 1.0) * kS32Scale;
        return static_cast<int32_t>(std::clamp(scaled, -kS32Scale, kS32Scale - 1));
      }
      }
    }

    float ReadFloat(const uint8_t *data, SampleType type) {
      switch (type) {
      case SampleType::U8:
        return static_cast<float>((static_cast<int>(*data) - kU8Offset) / kU8Scale);
      case SampleType::S16:
        return static_cast<float>(Load<int16_t>(data) / kS16Scale);
      case SampleType::S32:
        return static_cast<float>(Load<int32_t>(data) / kS32Scale);
      default:
        return Load<float>(data);
      }
    }

    void Convert(const uint8_t *from, SampleType fromType, uint8_t *target, SampleType toType) {
      if (fromType == toType) {
        std::memcpy(target, from, Size(toType));
        return;
      }
      switch (toType) {
      case SampleType::F32:
        Store(target, ReadFloat(from, fromType));
        break;
      case SampleType::S32:
        Store(target, ReadInt(from, fromType));
        break;
      case SampleType::S16:
        Store(target, static_cast<int16_t>(ReadInt(from, fromType) >> kS16Shift));
        break;
      case SampleType::U8:
        *target = static_cast<uint8_t>((ReadInt(from, fromType) >> kU8Shift) + kU8Offset);
        break;
      }
    }

  } // namespace

  void AudioSamples::Init(pybind11::module &m) {
    m.def("copyAudioSamples", &AudioSamples::Copy, pybind11::arg("source"), pybind11::arg("sourceFormat"),
          pybind11::arg("channels"), pybind11::arg("frames"), pybind11::arg("destination"),
          pybind11::arg("destinationFormat"), pybind11::arg("planeIndex"), pybind11::arg("frameOffset"),
          pybind11::arg("frameCount"));
  }

  void AudioSamples::Copy(const pybind11::buffer &source, const std::string &sourceFormatName, size_t channels,
                          size_t frames, const pybind11::buffer &destination, const std::string &destinationFormatName,
                          size_t planeIndex, size_t frameOffset, size_t frameCount) {
    auto sourceFormat = ParseFormat(sourceFormatName);
    auto destinationFormat = ParseFormat(destinationFormatName);
    auto sourceInfo = ContiguousBuffer(source);
    auto destinationInfo = ContiguousBuffer(destination, true);
    auto sourceSize = static_cast<size_t>(sourceInfo.size * sourceInfo.itemsize);
    auto destinationSize = static_cast<size_t>(destinationInfo.size * destinationInfo.itemsize);
    const size_t sourceSample = Size(sourceFormat.type);
    const size_t destinationSample = Size(destinationFormat.type);
    const size_t copiedChannels = destinationFormat.planar ? 1 : channels;

    // divided rather than multiplied, which could overflow
    if (channels == 0 || frameOffset > frames || frameCount > frames - frameOffset ||
        frames > sourceSize / sourceSample / channels ||
        frameCount > destinationSize / destinationSample / copiedChannels ||
        (destinationFormat.planar ? planeIndex >= channels : planeIndex != 0)) {
      throw pybind11::value_error("The copy is out of the bounds of the samples or of the destination");
    }

    const auto *from = static_cast<const uint8_t *>(sourceInfo.ptr);
    auto *target = static_cast<uint8_t *>(destinationInfo.ptr);
    const gil_release release;
    for (size_t frame = 0; frame < frameCount; ++frame) {
      for (size_t copied = 0; copied < copiedChannels; ++copied) {
        const size_t channel = destinationFormat.planar ? planeIndex : copied;
        const size_t sourceIndex = sourceFormat.planar ? (channel * frames) + frameOffset + frame
                                                       : ((frameOffset + frame) * channels) + channel;
        const size_t destinationIndex = (frame * copiedChannels) + copied;
        Convert(from + (sourceIndex * sourceSample), sourceFormat.type, target + (destinationIndex * destinationSample),
                destinationFormat.type);
      }
    }
  }

} // namespace python_webrtc
