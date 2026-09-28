//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>

#include "../interfaces/media_stream.h"

namespace python_webrtc {

  // A stream of a synthetic microphone and camera
  // (https://github.com/MarshalX/python-webrtc/issues/169, https://github.com/MarshalX/python-webrtc/issues/170)
  std::shared_ptr<MediaStream> GetUserMedia(bool audio, bool video, int width, int height, double frameRate);

}
