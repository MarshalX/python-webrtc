//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "media_type.h"

#include <api/media_types.h>

namespace python_webrtc {

  void MediaType::Init(pybind11::module &m) {
    pybind11::enum_<cricket::MediaType>(m, "MediaType")
        .value("audio", cricket::MediaType::MEDIA_TYPE_AUDIO)
        .value("video", cricket::MediaType::MEDIA_TYPE_VIDEO)
        .value("data", cricket::MediaType::MEDIA_TYPE_DATA)
        .value("unsupported", cricket::MediaType::MEDIA_TYPE_UNSUPPORTED)
        .export_values();
  }
} // namespace python_webrtc
