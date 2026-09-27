//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "peer_connection_factory.h"
#include "../utils/gil.h"

#include <api/audio/create_audio_device_module.h>
#include <api/create_peerconnection_factory.h>
#include <api/environment/environment_factory.h>
#include <api/audio_codecs/builtin_audio_encoder_factory.h>
#include <api/audio_codecs/builtin_audio_decoder_factory.h>
#include <api/video_codecs/builtin_video_encoder_factory.h>
#include <api/video_codecs/builtin_video_decoder_factory.h>
#include <rtc_base/ssl_adapter.h>

namespace python_webrtc {

  PeerConnectionFactory *PeerConnectionFactory::_default = nullptr;
  std::mutex PeerConnectionFactory::_mutex{};
  int PeerConnectionFactory::_references = 0;

  PeerConnectionFactory::PeerConnectionFactory() {
    _workerThread = webrtc::Thread::CreateWithSocketServer();
    assert(_workerThread);

    bool result = _workerThread->SetName("PeerConnectionFactory:workerThread", nullptr);
    assert(result);

    result = _workerThread->Start();
    assert(result);

    _signalingThread = webrtc::Thread::Create();
    assert(_signalingThread);

    result = _signalingThread->SetName("PeerConnectionFactory:signalingThread", nullptr);
    assert(result);

    result = _signalingThread->Start();
    assert(result);

    _workerThread->BlockingCall([this]() {
      _audioDeviceModule = webrtc::CreateAudioDeviceModule(
          webrtc::CreateEnvironment(), webrtc::AudioDeviceModule::AudioLayer::kDummyAudio);
    });

    _factory = webrtc::CreatePeerConnectionFactory(
        _workerThread.get(),
        _workerThread.get(),
        _signalingThread.get(),
        _audioDeviceModule,
        webrtc::CreateBuiltinAudioEncoderFactory(),
        webrtc::CreateBuiltinAudioDecoderFactory(),
        webrtc::CreateBuiltinVideoEncoderFactory(),
        webrtc::CreateBuiltinVideoDecoderFactory(),
        nullptr,
        nullptr);
    assert(_factory);

    webrtc::PeerConnectionFactoryInterface::Options options;
    options.network_ignore_mask = 0;
    _factory->SetOptions(options);
  }

  PeerConnectionFactory::~PeerConnectionFactory() {
    _factory = nullptr;

    _workerThread->BlockingCall([this]() {
      this->_audioDeviceModule = nullptr;
    });

    _workerThread->Stop();
    _signalingThread->Stop();

    _workerThread = nullptr;
    _signalingThread = nullptr;
  }

  PeerConnectionFactory *PeerConnectionFactory::GetOrCreateDefault() {
    _mutex.lock();
    _references++;
    if (_references == 1) {
      assert(_default == nullptr);
      auto factory = new PeerConnectionFactory();
      _default = factory;
    }
    _mutex.unlock();
    return _default;
  }

  void PeerConnectionFactory::Release() {
    _mutex.lock();
    _references--;
    assert(_references >= 0);
    if (!_references) {
      assert(_default != nullptr);
      _default = nullptr;
    }
    _mutex.unlock();
  }

  void PeerConnectionFactory::Dispose() {
    webrtc::CleanupSSL();
  }

  void PeerConnectionFactory::Init(pybind11::module &m) {
    bool result;
    (void) result;

    result = webrtc::InitializeSSL();
    assert(result);

    pybind11::class_<PeerConnectionFactory>(m, "PeerConnectionFactory")
        .def(pybind11::init<>(), nogil())
        .def("getOrCreateDefault", &PeerConnectionFactory::GetOrCreateDefault, nogil())
        .def("release", &PeerConnectionFactory::Release, nogil())
        .def("dispose", &PeerConnectionFactory::Dispose, nogil());
  }

} // namespace python_webrtc
