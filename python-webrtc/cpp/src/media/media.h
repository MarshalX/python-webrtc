//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_MEDIA_H_
#define PYTHON_WEBRTC_MEDIA_MEDIA_H_

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Media the application reads from tracks and writes to them: frames, processors and generators
  class Media {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_MEDIA_H_
