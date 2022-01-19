//
// Created by Il'ya Semyonov on 1/19/22.
//

#pragma once

#include <cstdint>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class RTCOnDataEvent {
  public:
    RTCOnDataEvent(std::string &, uint16_t);

    static void Init(pybind11::module &m);

    uint8_t* audioData;
    uint16_t numberOfFrames;
    uint16_t sampleRate = 48000;
    uint8_t bitsPerSample = 16;
    uint8_t channelCount = 1;
  };

} // namespace python_webrtc
