//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <pybind11/pybind11.h>
#include <api/rtp_transceiver_interface.h>

#include "../../utils/absl_optional.h"

namespace python_webrtc {

  static void bindRtpEncodingParameters(pybind11::module &m) {
    pybind11::class_<webrtc::RtpEncodingParameters>(m, "RtpEncodingParameters")
        .def(pybind11::init<>())
        .def_readwrite("active", &webrtc::RtpEncodingParameters::active)
        .def_readwrite("maxBitrate", &webrtc::RtpEncodingParameters::max_bitrate_bps)
        .def_readwrite("maxFramerate", &webrtc::RtpEncodingParameters::max_framerate)
        .def_readwrite("rid", &webrtc::RtpEncodingParameters::rid)
        .def_readwrite("scaleResolutionDownBy", &webrtc::RtpEncodingParameters::scale_resolution_down_by)
        // mb add bitrate_priority as "priority" and bind double values to enum members (low, high and so on)
        .def_readwrite("ssrc", &webrtc::RtpEncodingParameters::ssrc);
  }

} // namespace python_webrtc
