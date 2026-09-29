//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_
#define PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include <api/media_stream_interface.h>

namespace python_webrtc {

  class RTCVideoTrackSource;

  // The device behind a get_user_media track, whose source libwebrtc hides behind a proxy; keyed by address and id
  class SourceControl {
  public:
    std::mutex mutex;
    // the synthetic camera, cleared when it's destroyed
    RTCVideoTrackSource *camera = nullptr;
    bool microphone = false;

    static void Register(const webrtc::MediaStreamTrackInterface *track, const std::string &trackId,
                         const std::shared_ptr<SourceControl> &control) {
      const std::scoped_lock lock(RegistryMutex());
      auto &registry = Registry();
      for (auto it = registry.begin(); it != registry.end();) {
        it = it->second.expired() ? registry.erase(it) : std::next(it);
      }
      registry[{track, trackId}] = control;
    }

    static std::shared_ptr<SourceControl> Find(const webrtc::MediaStreamTrackInterface *track,
                                               const std::string &trackId) {
      const std::scoped_lock lock(RegistryMutex());
      auto &registry = Registry();
      auto it = registry.find({track, trackId});
      return it != registry.end() ? it->second.lock() : nullptr;
    }

  private:
    // both: a loopback remote track shares the id, and an address may be reused
    using Key = std::pair<const webrtc::MediaStreamTrackInterface *, std::string>;
    using Map = std::map<Key, std::weak_ptr<SourceControl>>;

    static Map &Registry() {
      // never destroyed: wrappers may outlive static destructors
      static auto *registry = new Map();
      return *registry;
    }

    static std::mutex &RegistryMutex() {
      static auto *mutex = new std::mutex();
      return *mutex;
    }
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_SOURCE_CONTROL_H_
