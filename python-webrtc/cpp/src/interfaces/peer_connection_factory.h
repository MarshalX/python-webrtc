//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>
#include <mutex>

#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>
#include <rtc_base/thread.h>
#include <modules/audio_device/include/audio_device.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace webrtc {

  class PeerConnectionFactoryInterface;

}  // namespace webrtc

namespace python_webrtc {

  // Owned by every wrapper created with it, it's destroyed together with the last of them.
  class PeerConnectionFactory {
  public:
    explicit PeerConnectionFactory();

    ~PeerConnectionFactory();

    static std::shared_ptr<PeerConnectionFactory> Create();

    // The factory shared by everything created without an explicit one, alive while anything uses it.
    static std::shared_ptr<PeerConnectionFactory> GetOrCreateDefault();

    webrtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> factory() { return _factory; }

    static void Init(pybind11::module &m);

    static void Dispose();

    std::unique_ptr<webrtc::Thread> _signalingThread;
    std::unique_ptr<webrtc::Thread> _workerThread;

  private:
    // of the process the factory was created in (see forks)
    const int _generation;

    static void Destroy(PeerConnectionFactory *);

    static std::weak_ptr<PeerConnectionFactory> _default;
    static std::mutex _mutex;
    // factories constructed and not destroyed yet, lets tests check that none leaks
    static std::atomic<int> _alive;

    webrtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> _factory;
    webrtc::scoped_refptr<webrtc::AudioDeviceModule> _audioDeviceModule;
  };

} // namespace python_webrtc
