//
// Created by Il'ya Semyonov on 1/4/22.
//

#include <api/create_peerconnection_factory.h>
#include <api/audio_codecs/builtin_audio_encoder_factory.h>
#include <api/audio_codecs/builtin_audio_decoder_factory.h>
#include <api/video_codecs/builtin_video_encoder_factory.h>
#include <api/video_codecs/builtin_video_decoder_factory.h>
#include <p2p/base/basic_packet_socket_factory.h>
#include <rtc_base/ssl_adapter.h>

#include "peer_connection_factory.h"

namespace python_webrtc {

  PeerConnectionFactory *PeerConnectionFactory::_default = nullptr;
  std::mutex PeerConnectionFactory::_mutex{};
  int PeerConnectionFactory::_references = 0;

  PeerConnectionFactory::PeerConnectionFactory() {
    _workerThread = rtc::Thread::CreateWithSocketServer();
    assert(_workerThread);

    bool result = _workerThread->SetName("PeerConnectionFactory:workerThread", nullptr);
    assert(result);

    result = _workerThread->Start();
    assert(result);

    _signalingThread = rtc::Thread::Create();
    assert(_signalingThread);

    result = _signalingThread->SetName("PeerConnectionFactory:signalingThread", nullptr);
    assert(result);

    result = _signalingThread->Start();
    assert(result);

    _factory = webrtc::CreatePeerConnectionFactory(
        _workerThread.get(),
        _workerThread.get(),
        _signalingThread.get(),
        _audioDeviceModule.get(),
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

    _networkManager = std::unique_ptr<rtc::NetworkManager>(new rtc::BasicNetworkManager());
    assert(_networkManager != nullptr);

    _socketFactory = std::unique_ptr<rtc::PacketSocketFactory>(new rtc::BasicPacketSocketFactory(_workerThread.get()));
    assert(_socketFactory != nullptr);
  }

  PeerConnectionFactory::~PeerConnectionFactory() {
    _factory = nullptr;

    _workerThread->Invoke<void>(RTC_FROM_HERE, [this]() {
      this->_audioDeviceModule = nullptr;
    });

    _workerThread->Stop();
    _signalingThread->Stop();

    _workerThread = nullptr;
    _signalingThread = nullptr;

    _networkManager = nullptr;
    _socketFactory = nullptr;
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
    rtc::CleanupSSL();
  }

  void PeerConnectionFactory::Init(py::module &m) {
    bool result;
    (void) result;

    result = rtc::InitializeSSL();
    assert(result);

    py::class_<PeerConnectionFactory>(m, "PeerConnectionFactory")
        .def(py::init<>())
        .def("GetOrCreateDefault", &PeerConnectionFactory::GetOrCreateDefault)
        .def("Release", &PeerConnectionFactory::Release)
        .def("factory", &PeerConnectionFactory::factory)
//         TODO mb
//        .def("getNetworkManager", &PeerConnectionFactory::getNetworkManager)
//        .def("getSocketFactory", &PeerConnectionFactory::getSocketFactory)
        .def("Dispose", &PeerConnectionFactory::Dispose);
  }

} // namespace python_webrtc
