#include <webrtc/api/audio_codecs/builtin_audio_decoder_factory.h>
#include <webrtc/api/audio_codecs/builtin_audio_encoder_factory.h>
#include <webrtc/api/create_peerconnection_factory.h>
#include <webrtc/api/video_codecs/builtin_video_decoder_factory.h>
#include <webrtc/api/video_codecs/builtin_video_encoder_factory.h>
#include <webrtc/api/video_codecs/video_decoder_factory.h>
#include <webrtc/rtc_base/location.h>
#include <webrtc/rtc_base/thread.h>
#include <p2p/base/basic_packet_socket_factory.h>

#include <pybind11/pybind11.h>

namespace py = pybind11;

void ping() {
  auto _workerThread = rtc::Thread::CreateWithSocketServer();
  assert(_workerThread);

  bool result = _workerThread->SetName("PeerConnectionFactory:workerThread", nullptr);
  assert(result);

  result = _workerThread->Start();
  assert(result);

  auto _signalingThread = rtc::Thread::Create();
  assert(_signalingThread);

  result = _signalingThread->SetName("PeerConnectionFactory:signalingThread", nullptr);
  assert(result);

  result = _signalingThread->Start();
  assert(result);

  auto _factory = webrtc::CreatePeerConnectionFactory(
      _workerThread.get(),
      _workerThread.get(),
      _signalingThread.get(),
      nullptr,
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

  auto _networkManager = std::unique_ptr<rtc::NetworkManager>(new rtc::BasicNetworkManager());
  assert(_networkManager != nullptr);

  auto _socketFactory = std::unique_ptr<rtc::PacketSocketFactory>(
      new rtc::BasicPacketSocketFactory(_workerThread.get()));
  assert(_socketFactory != nullptr);

  py::print("successfully create peer connection factory");
}

PYBIND11_MODULE(webrtc, m) {
  m.def("ping", &ping);
}
