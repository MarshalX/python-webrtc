//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "peer_connection_factory.h"
#include "../media/playout_audio_device.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

#include <api/create_peerconnection_factory.h>
#include <api/make_ref_counted.h>
#include <api/audio_codecs/builtin_audio_encoder_factory.h>
#include <api/audio_codecs/builtin_audio_decoder_factory.h>
#include <api/video_codecs/video_decoder_factory_template.h>
#include <api/video_codecs/video_decoder_factory_template_dav1d_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp9_adapter.h>
#include <api/video_codecs/video_encoder_factory_template.h>
#include <api/video_codecs/video_encoder_factory_template_libaom_av1_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp9_adapter.h>
#include <rtc_base/ssl_adapter.h>

#include <thread>

namespace python_webrtc {

  // Royalty-free codecs only (the prebuilts have no H.264).
  using VideoEncoderFactory = webrtc::VideoEncoderFactoryTemplate<
      webrtc::LibvpxVp8EncoderTemplateAdapter,
      webrtc::LibvpxVp9EncoderTemplateAdapter,
      webrtc::LibaomAv1EncoderTemplateAdapter>;

  using VideoDecoderFactory = webrtc::VideoDecoderFactoryTemplate<
      webrtc::LibvpxVp8DecoderTemplateAdapter,
      webrtc::LibvpxVp9DecoderTemplateAdapter,
      webrtc::Dav1dDecoderTemplateAdapter>;

  std::weak_ptr<PeerConnectionFactory> PeerConnectionFactory::_default{};
  std::mutex PeerConnectionFactory::_mutex{};
  std::atomic<int> PeerConnectionFactory::_alive{0};

  PeerConnectionFactory::PeerConnectionFactory() {
    _alive++;

    _workerThread = webrtc::Thread::CreateWithSocketServer();
    assert(_workerThread);

    // checked by assert only, in debug builds
    [[maybe_unused]] bool result = _workerThread->SetName("PeerConnectionFactory:workerThread", nullptr);
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
      onLibwebrtcThread = true;
      _audioDeviceModule = webrtc::make_ref_counted<PlayoutAudioDevice>();
    });
    _signalingThread->BlockingCall([]() { onLibwebrtcThread = true; });

    _factory = webrtc::CreatePeerConnectionFactory(
        _workerThread.get(),
        _workerThread.get(),
        _signalingThread.get(),
        _audioDeviceModule,
        webrtc::CreateBuiltinAudioEncoderFactory(),
        webrtc::CreateBuiltinAudioDecoderFactory(),
        std::make_unique<VideoEncoderFactory>(),
        std::make_unique<VideoDecoderFactory>(),
        nullptr,
        nullptr);
    assert(_factory);

    webrtc::PeerConnectionFactoryInterface::Options options;
    options.network_ignore_mask = 0;
    _factory->SetOptions(options);
  }

  PeerConnectionFactory::~PeerConnectionFactory() {
    // stopping the threads waits for their tasks, which may be waiting for the GIL
    BlockingDestructor release("PeerConnectionFactory");

    _factory = nullptr;

    _workerThread->BlockingCall([this]() {
      this->_audioDeviceModule = nullptr;
    });

    _workerThread->Stop();
    _signalingThread->Stop();

    _workerThread = nullptr;
    _signalingThread = nullptr;

    _alive--;
  }

  std::shared_ptr<PeerConnectionFactory> PeerConnectionFactory::Create() {
    return {new PeerConnectionFactory(), &PeerConnectionFactory::Destroy};
  }

  std::shared_ptr<PeerConnectionFactory> PeerConnectionFactory::GetOrCreateDefault() {
    std::lock_guard<std::mutex> lock(_mutex);
    auto factory = _default.lock();
    if (!factory) {
      factory = Create();
      _default = factory;
    }
    return factory;
  }

  void PeerConnectionFactory::Destroy(PeerConnectionFactory *factory) {
    // the last owner may be released by a task on one of the factory threads, which can't stop itself
    if (factory->_workerThread->IsCurrent() || factory->_signalingThread->IsCurrent()) {
      std::thread([factory]() { delete factory; }).detach();
      return;
    }

    delete factory;
  }

  void PeerConnectionFactory::Dispose() {
    webrtc::CleanupSSL();
  }

  void PeerConnectionFactory::Init(pybind11::module &m) {
    [[maybe_unused]] bool result = webrtc::InitializeSSL();
    assert(result);

    pybind11::class_<PeerConnectionFactory, std::shared_ptr<PeerConnectionFactory>>(m, "PeerConnectionFactory")
        .def(pybind11::init(&PeerConnectionFactory::Create), nogil())
        .def_static("getOrCreateDefault", &PeerConnectionFactory::GetOrCreateDefault, nogil())
        .def_static("dispose", &PeerConnectionFactory::Dispose, nogil());

    m.def("_alive_factories", []() { return _alive.load(); });
  }

} // namespace python_webrtc
