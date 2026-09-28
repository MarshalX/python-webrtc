//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "enums.h"

namespace python_webrtc {

  std::optional<webrtc::MediaType> mediaTypeOf(const std::string &kind) {
    if (kind == "audio") {
      return webrtc::MediaType::AUDIO;
    }
    if (kind == "video") {
      return webrtc::MediaType::VIDEO;
    }
    return std::nullopt;
  }

} // namespace python_webrtc
