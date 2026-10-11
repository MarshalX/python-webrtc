//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_PEER_CONNECTION_FACTORY_H_
#define PYTHON_WEBRTC_INTERFACES_PEER_CONNECTION_FACTORY_H_

#include <memory>
#include <mutex>
#include <string>

#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>
#include <modules/audio_device/include/audio_device.h>
#include <rtc_base/thread.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../utils/field_trials.h"
#include "../utils/native_object.h"

namespace python_webrtc {

  // Owned by every wrapper created with it, it's destroyed together with the last of them.
  class PeerConnectionFactory : public NativeObject<PeerConnectionFactory> {
  public:
    static constexpr const char *kName = "PeerConnectionFactory";

    explicit PeerConnectionFactory();

    ~PeerConnectionFactory();

    PeerConnectionFactory(const PeerConnectionFactory &) = delete;
    PeerConnectionFactory &operator=(const PeerConnectionFactory &) = delete;

    static std::shared_ptr<PeerConnectionFactory> Create();

    // The factory shared by everything created without an explicit one, alive while anything uses it.
    static std::shared_ptr<PeerConnectionFactory> GetOrCreateDefault();

    webrtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> factory() { return _factory; }

    static void Init(pybind11::module &m);

    static void Dispose();

    webrtc::Thread *signalingThread() { return _signalingThread.get(); }

    webrtc::Thread *workerThread() { return _workerThread.get(); }

    [[nodiscard]] bool IsCurrent() const { return _signalingThread->IsCurrent() || _workerThread->IsCurrent(); }

    // before the first factory only
    static void SetFieldTrials(const std::string &trials);
    static void AllowLoopback();

    [[nodiscard]] const FieldTrials &fieldTrials() const { return _fieldTrials; }

    [[nodiscard]] int networkIgnoreMask() const { return _networkIgnoreMask; }

  private:
    std::unique_ptr<webrtc::Thread> _signalingThread;
    std::unique_ptr<webrtc::Thread> _workerThread;

    const FieldTrials _fieldTrials;
    const int _networkIgnoreMask;

    // _mutex held
    static std::shared_ptr<PeerConnectionFactory> CreateLocked();
    static void InitializeSSL();
    static void ThrowIfStarted(const std::string &what);

    static std::weak_ptr<PeerConnectionFactory> _default;
    static std::mutex _mutex;
    static bool _sslInitialized;
    static FieldTrials _trials;
    static bool _loopbackAllowed;
    static bool _started;

    webrtc::scoped_refptr<webrtc::PeerConnectionFactoryInterface> _factory;
    webrtc::scoped_refptr<webrtc::AudioDeviceModule> _audioDeviceModule;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_PEER_CONNECTION_FACTORY_H_
