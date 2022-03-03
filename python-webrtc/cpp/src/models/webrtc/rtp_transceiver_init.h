//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <pybind11/pybind11.h>
#include <api/rtp_transceiver_interface.h>

namespace python_webrtc {

  static void bindRtpTransceiverInit(pybind11::module &m) {
    pybind11::class_<webrtc::RtpTransceiverInit>(m, "RtpTransceiverInit")
        .def(pybind11::init<>())
        .def_readwrite("direction", &webrtc::RtpTransceiverInit::direction)
        .def_readwrite("streamIds", &webrtc::RtpTransceiverInit::stream_ids)
        .def_readwrite("sendEncodings", &webrtc::RtpTransceiverInit::send_encodings);
  }

} // namespace python_webrtc
