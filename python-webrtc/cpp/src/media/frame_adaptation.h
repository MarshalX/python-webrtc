//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_FRAME_ADAPTATION_H_
#define PYTHON_WEBRTC_MEDIA_FRAME_ADAPTATION_H_

#include <optional>

#include <api/video/video_adapter.h>
#include <api/video/video_frame.h>
#include <rtc_base/time_utils.h>

namespace python_webrtc {

  // The frame as the adapter's sinks want it, timed by its capture time: cropped and scaled, or none when dropped
  inline std::optional<webrtc::VideoFrame> AdaptFrame(webrtc::VideoAdapter &adapter, const webrtc::VideoFrame &frame) {
    int croppedWidth = 0;
    int croppedHeight = 0;
    int width = 0;
    int height = 0;
    if (!adapter.AdaptFrameResolution(frame.width(), frame.height(),
                                      frame.timestamp_us() * webrtc::kNumNanosecsPerMicrosec, &croppedWidth,
                                      &croppedHeight, &width, &height)) {
      return std::nullopt;
    }
    if (width == frame.width() && height == frame.height()) {
      return frame;
    }
    webrtc::VideoFrame adapted = frame;
    adapted.set_video_frame_buffer(frame.video_frame_buffer()->CropAndScale(
        (frame.width() - croppedWidth) / 2, (frame.height() - croppedHeight) / 2, croppedWidth, croppedHeight, width,
        height));
    adapted.clear_update_rect();
    return adapted;
  }

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_FRAME_ADAPTATION_H_
