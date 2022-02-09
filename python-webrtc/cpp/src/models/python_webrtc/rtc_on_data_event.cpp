//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_on_data_event.h"

namespace python_webrtc {

  RTCOnDataEvent::RTCOnDataEvent(std::string &data, uint16_t length) {
    audioData = reinterpret_cast<uint8_t *>(data.data());
    numberOfFrames = length;
  }

  void RTCOnDataEvent::Init(pybind11::module &m) {
    pybind11::class_<RTCOnDataEvent>(m, "RTCOnDataEvent")
        .def(pybind11::init<std::string &, uint16_t>())
        .def_readwrite("audioData", &RTCOnDataEvent::audioData)
        .def_readwrite("bitsPerSample", &RTCOnDataEvent::bitsPerSample)
        .def_readwrite("sampleRate", &RTCOnDataEvent::sampleRate)
        .def_readwrite("channelCount", &RTCOnDataEvent::channelCount)
        .def_readwrite("numberOfFrames", &RTCOnDataEvent::numberOfFrames);

  }

} // namespace python_webrtc
