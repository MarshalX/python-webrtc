//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_LOCAL_VIDEO_SINK_H_
#define PYTHON_WEBRTC_MEDIA_LOCAL_VIDEO_SINK_H_

#include <mutex>
#include <set>

#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>

#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  // A sink of ours on a track (a processor, a monitor): it sees the frames of the track's source, never the ones a
  // source adapts for an encoder. Registered while it exists, as sinks reach a source through libwebrtc's tracks.
  class LocalVideoSink : public webrtc::VideoSinkInterface<webrtc::VideoFrame> {
  public:
    LocalVideoSink() {
      auto &sinks = Sinks();
      const std::scoped_lock lock(sinks.mutex);
      sinks.sinks.insert(this);
    }

    ~LocalVideoSink() override {
      auto &sinks = Sinks();
      const std::scoped_lock lock(sinks.mutex);
      sinks.sinks.erase(this);
    }

    LocalVideoSink(const LocalVideoSink &) = delete;
    LocalVideoSink &operator=(const LocalVideoSink &) = delete;

    static bool Is(const webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) {
      auto &sinks = Sinks();
      const std::scoped_lock lock(sinks.mutex);
      return sinks.sinks.contains(sink);
    }

  private:
    struct Registry {
      std::mutex mutex;
      std::set<const webrtc::VideoSinkInterface<webrtc::VideoFrame> *> sinks;
    };

    static Registry &Sinks() {
      static ForkLocal<Registry> registry;
      return registry.Get();
    }
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_LOCAL_VIDEO_SINK_H_
