//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <mutex>

#include <webrtc/api/peer_connection_interface.h>
#include <webrtc/api/scoped_refptr.h>
#include <webrtc/modules/audio_device/include/audio_device.h>

#include <pybind11/pybind11.h>

namespace rtc {

  class NetworkManager;

  class PacketSocketFactory;

  class Thread;

}  // namespace rtc

namespace webrtc {

  class PeerConnectionFactoryInterface;

}  // namespace webrtc

namespace python_webrtc {

  class PeerConnectionFactory {
  public:
    explicit PeerConnectionFactory();

    ~PeerConnectionFactory();

    static PeerConnectionFactory *GetOrCreateDefault();

    static void Release();

    rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> factory() { return _factory; }

    rtc::NetworkManager *getNetworkManager() { return _networkManager.get(); }

    rtc::PacketSocketFactory *getSocketFactory() { return _socketFactory.get(); }

    static void Init(pybind11::module &m);

    static void Dispose();

    std::unique_ptr<rtc::Thread> _signalingThread;
    std::unique_ptr<rtc::Thread> _workerThread;

  private:
    static PeerConnectionFactory *_default;
    static std::mutex _mutex;
    static int _references;

    rtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> _factory;
    rtc::scoped_refptr<webrtc::AudioDeviceModule> _audioDeviceModule;

    std::unique_ptr<rtc::NetworkManager> _networkManager;
    std::unique_ptr<rtc::PacketSocketFactory> _socketFactory;
  };

} // namespace python_webrtc
