//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_WEBRTC_RTP_PARAMETERS_H_
#define PYTHON_WEBRTC_MODELS_WEBRTC_RTP_PARAMETERS_H_

#include <pybind11/pybind11.h>

#include "../../enums/enums.h"

namespace python_webrtc {

  // The structs of api/rtp_parameters.h as plain values; webrtc.models.rtp_parameters converts them to Python models
  void bindRtpParameters(pybind11::module &m);

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_WEBRTC_RTP_PARAMETERS_H_
