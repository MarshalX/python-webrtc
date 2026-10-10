//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_
#define PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_

#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <utility>

#include <api/media_stream_interface.h>

#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  class RTCVideoTrackSource;

  // The device behind a get_user_media track, whose source libwebrtc hides behind a proxy; keyed by address and id
  class SourceControl {
  public:
    std::mutex mutex;
    // the synthetic camera, cleared when it's destroyed
    RTCVideoTrackSource *camera = nullptr;
    bool microphone = false;
    // tracks not ended
    std::set<const webrtc::MediaStreamTrackInterface *> live;

    static void Register(const webrtc::MediaStreamTrackInterface *track, const std::string &trackId,
                         const std::shared_ptr<SourceControl> &control) {
      auto &registry = Registry();
      const std::scoped_lock lock(registry.mutex);
      for (auto it = registry.controls.begin(); it != registry.controls.end();) {
        it = it->second.expired() ? registry.controls.erase(it) : std::next(it);
      }
      registry.controls[{track, trackId}] = control;
      const std::scoped_lock controlLock(control->mutex);
      control->live.insert(track);
    }

    void Ended(const webrtc::MediaStreamTrackInterface *track) {
      const std::scoped_lock lock(mutex);
      live.erase(track);
    }

    bool AnyLive() {
      const std::scoped_lock lock(mutex);
      return !live.empty();
    }

    static std::shared_ptr<SourceControl> Find(const webrtc::MediaStreamTrackInterface *track,
                                               const std::string &trackId) {
      auto &registry = Registry();
      const std::scoped_lock lock(registry.mutex);
      auto it = registry.controls.find({track, trackId});
      return it != registry.controls.end() ? it->second.lock() : nullptr;
    }

  private:
    // both: a loopback remote track shares the id, and an address may be reused
    using Key = std::pair<const webrtc::MediaStreamTrackInterface *, std::string>;

    struct Controls {
      std::mutex mutex;
      std::map<Key, std::weak_ptr<SourceControl>> controls;
    };

    static Controls &Registry() {
      static ForkLocal<Controls> registry;
      return registry.Get();
    }
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_
