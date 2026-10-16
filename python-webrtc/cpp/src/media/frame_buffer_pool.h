//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_FRAME_BUFFER_POOL_H_
#define PYTHON_WEBRTC_MEDIA_FRAME_BUFFER_POOL_H_

#include <cstddef>
#include <mutex>
#include <optional>

#include <api/scoped_refptr.h>
#include <api/video/i420_buffer.h>
#include <api/video/nv12_buffer.h>
#include <api/video/video_frame_buffer.h>
#include <common_video/include/video_frame_buffer_pool.h>

namespace python_webrtc {

  // Frame buffers recycled once their frames are gone, for any thread: a new buffer when all of the pool's are in use
  class FrameBufferPool {
  public:
    static constexpr size_t kDefaultSize = 8;

    void Resize(std::optional<int> size) {
      const std::scoped_lock lock(_mutex);
      _pool.Resize(size && *size > 0 ? static_cast<size_t>(*size) : kDefaultSize);
    }

    webrtc::scoped_refptr<webrtc::I420Buffer> CreateI420(int width, int height) {
      {
        const std::scoped_lock lock(_mutex);
        if (auto buffer = _pool.CreateI420Buffer(width, height)) {
          return buffer;
        }
      }
      return webrtc::I420Buffer::Create(width, height);
    }

    webrtc::scoped_refptr<webrtc::NV12Buffer> CreateNV12(int width, int height) {
      {
        const std::scoped_lock lock(_mutex);
        if (auto buffer = _pool.CreateNV12Buffer(width, height)) {
          return buffer;
        }
      }
      return webrtc::NV12Buffer::Create(width, height);
    }

    webrtc::scoped_refptr<webrtc::VideoFrameBuffer> CropAndScale(webrtc::VideoFrameBuffer &buffer, int x, int y,
                                                                 int cropWidth, int cropHeight, int width, int height) {
      switch (buffer.type()) {
      case webrtc::VideoFrameBuffer::Type::kI420: {
        auto scaled = CreateI420(width, height);
        scaled->CropAndScaleFrom(*buffer.GetI420(), x, y, cropWidth, cropHeight);
        return scaled;
      }
      case webrtc::VideoFrameBuffer::Type::kNV12: {
        auto scaled = CreateNV12(width, height);
        scaled->CropAndScaleFrom(*buffer.GetNV12(), x, y, cropWidth, cropHeight);
        return scaled;
      }
      default:
        return buffer.CropAndScale(x, y, cropWidth, cropHeight, width, height);
      }
    }

  private:
    std::mutex _mutex;
    webrtc::VideoFrameBufferPool _pool{/*zero_initialize=*/false, kDefaultSize};
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_FRAME_BUFFER_POOL_H_
