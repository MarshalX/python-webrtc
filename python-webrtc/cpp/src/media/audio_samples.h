//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_AUDIO_SAMPLES_H_
#define PYTHON_WEBRTC_MEDIA_AUDIO_SAMPLES_H_

#include <cstddef>
#include <string>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Copies samples of AudioData (WebCodecs AudioSampleFormat), converting their format and layout
  class AudioSamples {
  public:
    static void Init(pybind11::module &m);

    // frames [frameOffset, frameOffset + frameCount): every channel if interleaved, channel planeIndex if planar
    static void Copy(const pybind11::buffer &source, const std::string &sourceFormat, size_t channels, size_t frames,
                     const pybind11::buffer &destination, const std::string &destinationFormat, size_t planeIndex,
                     size_t frameOffset, size_t frameCount);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_AUDIO_SAMPLES_H_
