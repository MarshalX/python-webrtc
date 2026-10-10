//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "peer_connection_factory.h"
#include "../codecs/openh264.h"
#include "../codecs/videotoolbox.h"
#include "../exceptions.h"
#include "../media/playout_audio_device.h"
#include "../utils/dispatcher.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

#include <api/audio_codecs/builtin_audio_decoder_factory.h>
#include <api/audio_codecs/builtin_audio_encoder_factory.h>
#include <api/create_peerconnection_factory.h>
#include <api/make_ref_counted.h>
#include <api/video_codecs/video_decoder_factory_template.h>
#include <api/video_codecs/video_decoder_factory_template_dav1d_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_decoder_factory_template_libvpx_vp9_adapter.h>
#include <api/video_codecs/video_encoder_factory_template.h>
#include <api/video_codecs/video_encoder_factory_template_libaom_av1_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp8_adapter.h>
#include <api/video_codecs/video_encoder_factory_template_libvpx_vp9_adapter.h>
#include <rtc_base/network.h>
#include <rtc_base/ssl_adapter.h>

#include <stdexcept>
#include <string>

#ifndef _WIN32
#include <pthread.h>
#endif

namespace python_webrtc {

#ifdef __APPLE__
  // the OS's H.264 first, it wins the formats both offer
  using VideoEncoderFactory = webrtc::VideoEncoderFactoryTemplate<
      webrtc::LibvpxVp8EncoderTemplateAdapter, webrtc::LibvpxVp9EncoderTemplateAdapter,
      webrtc::LibaomAv1EncoderTemplateAdapter, VideoToolboxEncoderAdapter, OpenH264EncoderAdapter>;

  using VideoDecoderFactory =
      webrtc::VideoDecoderFactoryTemplate<webrtc::LibvpxVp8DecoderTemplateAdapter,
                                          webrtc::LibvpxVp9DecoderTemplateAdapter, webrtc::Dav1dDecoderTemplateAdapter,
                                          VideoToolboxDecoderAdapter, OpenH264DecoderAdapter>;
#else
  // H.264 only once Cisco's OpenH264 binary is loaded (the prebuilts have none)
  using VideoEncoderFactory =
      webrtc::VideoEncoderFactoryTemplate<webrtc::LibvpxVp8EncoderTemplateAdapter,
                                          webrtc::LibvpxVp9EncoderTemplateAdapter,
                                          webrtc::LibaomAv1EncoderTemplateAdapter, OpenH264EncoderAdapter>;

  using VideoDecoderFactory =
      webrtc::VideoDecoderFactoryTemplate<webrtc::LibvpxVp8DecoderTemplateAdapter,
                                          webrtc::LibvpxVp9DecoderTemplateAdapter, webrtc::Dav1dDecoderTemplateAdapter,
                                          OpenH264DecoderAdapter>;
#endif

  std::weak_ptr<PeerConnectionFactory> PeerConnectionFactory::_default{};
  std::mutex PeerConnectionFactory::_mutex{};
  bool PeerConnectionFactory::_sslInitialized{false};
  FieldTrials PeerConnectionFactory::_trials{};
  bool PeerConnectionFactory::_loopbackAllowed{false};
  bool PeerConnectionFactory::_started{false};

  namespace {
    // NDEBUG compiles asserts out
    std::unique_ptr<webrtc::Thread> Started(std::unique_ptr<webrtc::Thread> thread, const char *name) {
      if (!thread || !thread->SetName(name, nullptr) || !thread->Start()) {
        throw RTCException(webrtc::RTCErrorType::INTERNAL_ERROR, std::string("Failed to start ") + name);
      }
      return thread;
    }
  } // namespace

  PeerConnectionFactory::PeerConnectionFactory()
      : _fieldTrials(_trials), _networkIgnoreMask(_loopbackAllowed ? 0 : webrtc::kDefaultNetworkIgnoreMask) {
    _workerThread = Started(webrtc::Thread::CreateWithSocketServer(), "PeerConnectionFactory:workerThread");
    _signalingThread = Started(webrtc::Thread::Create(), "PeerConnectionFactory:signalingThread");
    // sanitizer builds check that these threads never enter Python
    _workerThread->PostTask(&TagNativeThread);
    _signalingThread->PostTask(&TagNativeThread);

    BlockingCallOn(_workerThread, [this]() { _audioDeviceModule = webrtc::make_ref_counted<PlayoutAudioDevice>(); });

    _factory = webrtc::CreatePeerConnectionFactory(
        _workerThread.get(), _workerThread.get(), _signalingThread.get(), _audioDeviceModule,
        webrtc::CreateBuiltinAudioEncoderFactory(), webrtc::CreateBuiltinAudioDecoderFactory(),
        std::make_unique<VideoEncoderFactory>(), std::make_unique<VideoDecoderFactory>(), nullptr, nullptr, nullptr,
        _fieldTrials.CreateCopy());
    if (!_factory) {
      BlockingCallOn(_workerThread, [this]() { _audioDeviceModule = nullptr; });
      throw RTCException(webrtc::RTCErrorType::INTERNAL_ERROR, "Failed to create the peer connection factory");
    }

    webrtc::PeerConnectionFactoryInterface::Options options;
    options.network_ignore_mask = _networkIgnoreMask;
    _factory->SetOptions(options);
  }

  PeerConnectionFactory::~PeerConnectionFactory() {
    _factory = nullptr;

    BlockingCallOn(_workerThread, [this]() { this->_audioDeviceModule = nullptr; });

    _workerThread->Stop();
    _signalingThread->Stop();

    _workerThread = nullptr;
    _signalingThread = nullptr;
  }

  std::shared_ptr<PeerConnectionFactory> PeerConnectionFactory::Create() {
    const std::scoped_lock lock(_mutex);
    return CreateLocked();
  }

  std::shared_ptr<PeerConnectionFactory> PeerConnectionFactory::CreateLocked() {
#ifdef __APPLE__
    // libwebrtc runs its task queues on libdispatch, which crashes in the child of a fork
    if (Forks().load() > 0) {
      throw std::runtime_error(
          "python-webrtc can't be used in the child of a fork on macOS (libdispatch doesn't support "
          "it): use the spawn start method of multiprocessing");
    }
#endif
    InitializeSSL();
    _started = true;
    return NativeObject::Create();
  }

  void PeerConnectionFactory::SetFieldTrials(const std::string &trials) {
    const std::scoped_lock lock(_mutex);
    ThrowIfStarted("Field trials");
    const auto parsed = FieldTrials::Parse(trials);
    if (!parsed) {
      throw std::invalid_argument("Invalid field trials: '" + trials + "'");
    }
    _trials = *parsed;
  }

  void PeerConnectionFactory::AllowLoopback() {
    const std::scoped_lock lock(_mutex);
    ThrowIfStarted("Loopback");
    _loopbackAllowed = true;
  }

  void PeerConnectionFactory::ThrowIfStarted(const std::string &what) {
    if (_started) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE,
                         what + " can't change once the first RTCPeerConnection or RTCIceTransport is created");
    }
  }

  std::shared_ptr<PeerConnectionFactory> PeerConnectionFactory::GetOrCreateDefault() {
    const std::scoped_lock lock(_mutex);
    auto factory = _default.lock();
    if (!factory) {
      factory = CreateLocked();
      _default = factory;
    }
    return factory;
  }

  void PeerConnectionFactory::InitializeSSL() {
    if (!_sslInitialized) {
      if (!webrtc::InitializeSSL()) {
        throw RTCException(webrtc::RTCErrorType::INTERNAL_ERROR, "Failed to initialize SSL");
      }
      _sslInitialized = true;
    }
  }

  void PeerConnectionFactory::Dispose() {
    const std::scoped_lock lock(_mutex);
    if (Alive() > 0) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Failed to dispose: peer connection factories are alive");
    }
    if (_sslInitialized) {
      webrtc::CleanupSSL();
      _sslInitialized = false;
    }
  }

  void PeerConnectionFactory::Init(pybind11::module &m) {
    {
      const std::scoped_lock lock(_mutex);
      InitializeSSL();
    }

#ifndef _WIN32
    // libwebrtc threads don't survive a fork: the child forgets the factories (also runs before exec, keep it minimal)
    pthread_atfork(
        []() {
          _mutex.lock();
          Dispatcher::LockForFork();
        },
        []() {
          Dispatcher::UnlockAfterFork();
          _mutex.unlock();
        },
        []() {
          Forks()++;
          _default.reset();
          Dispatcher::UnlockAfterFork();
          _mutex.unlock();
        });
#endif

    pybind11::class_<PeerConnectionFactory, std::shared_ptr<PeerConnectionFactory>>(m, "PeerConnectionFactory")
        .def_property_readonly("_id", &PeerConnectionFactory::Id)
        .def(pybind11::init(nogil_factory(&PeerConnectionFactory::Create)))
        .def_static("getOrCreateDefault", &PeerConnectionFactory::GetOrCreateDefault, nogil())
        .def_static("dispose", &PeerConnectionFactory::Dispose, nogil());

    m.def("_alive_factories", &PeerConnectionFactory::Alive);
    m.def("_set_field_trials", &PeerConnectionFactory::SetFieldTrials, nogil(), pybind11::arg("trials"));
    m.def("_allow_loopback", &PeerConnectionFactory::AllowLoopback, nogil());
  }

} // namespace python_webrtc
