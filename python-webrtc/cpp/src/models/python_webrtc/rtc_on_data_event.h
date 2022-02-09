//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <cstdint>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class RTCOnDataEvent {
  public:
    RTCOnDataEvent(std::string &, uint16_t);

    static void Init(pybind11::module &m);

    uint8_t *audioData;
    uint16_t numberOfFrames;
    uint16_t sampleRate = 48000;
    uint8_t bitsPerSample = 16;
    uint8_t channelCount = 1;
  };

} // namespace python_webrtc
