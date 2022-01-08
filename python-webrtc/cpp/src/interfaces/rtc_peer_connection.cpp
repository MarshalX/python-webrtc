//
// Created by Il'ya Semyonov on 1/5/22.
//

#include "rtc_peer_connection.h"

#include <webrtc/p2p/client/basic_port_allocator.h>

#include "peer_connection_factory.h"
#include "create_session_description_observer.h"

namespace python_webrtc {

  RTCPeerConnection::RTCPeerConnection() {
    _factory = PeerConnectionFactory::GetOrCreateDefault();
    _shouldReleaseFactory = true;

//    TODO get from python
    auto configuration = new webrtc::PeerConnectionInterface::RTCConfiguration();

    auto portAllocator = std::unique_ptr<cricket::PortAllocator>(new cricket::BasicPortAllocator(
        _factory->getNetworkManager(),
        _factory->getSocketFactory())
    );

//    TODO get and set port range from configurator.
//    create some struct with min and max uint16_t fields. bind it to python
//    _port_range =  configurator (with additional fields)...port_range

    portAllocator->SetPortRange(0, 65535); // TODO get from config or default

//    TODO switch to CreatePeerConnectionOrError instead, because CreatePeerConnection is deprecated
    _jinglePeerConnection = _factory->factory()->CreatePeerConnection(
        *configuration, // TODO pass rtc configurator
        std::move(portAllocator),
        nullptr,
        this
    );
  }

  RTCPeerConnection::~RTCPeerConnection() {
    _jinglePeerConnection = nullptr;
    // TODO data channels
//    _channels.clear();
    if (_factory) {
      if (_shouldReleaseFactory) {
        PeerConnectionFactory::Release();
      }
      _factory = nullptr;
    }
  }

  void RTCPeerConnection::Init(pybind11::module &m) {
    pybind11::class_<RTCPeerConnection>(m, "RTCPeerConnection")
        .def(pybind11::init<>())
        .def("CreateOffer", &RTCPeerConnection::CreateOffer);
  }

  void RTCPeerConnection::SaveLastSdp(const RTCSessionDescriptionInit& lastSdp) {
    _lastSdp = lastSdp;
  }

  void RTCPeerConnection::CreateOffer(std::function<void(RTCSessionDescription)> &onSuccess) {
    if (!_jinglePeerConnection || _jinglePeerConnection->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
//      TODO call onFail
        return;
    }

    auto observer = new rtc::RefCountedObject<CreateSessionDescriptionObserver>(this, onSuccess);
//     TODO bind options
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    _jinglePeerConnection->CreateOffer(observer, options);
  }

  void RTCPeerConnection::OnSignalingChange(webrtc::PeerConnectionInterface::SignalingState new_state) {
//    TODO call python callback
    if (new_state == webrtc::PeerConnectionInterface::kClosed) {
//      TODO stop
    }
  }

  void RTCPeerConnection::OnIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) {

  }

  void RTCPeerConnection::OnIceGatheringChange(webrtc::PeerConnectionInterface::IceGatheringState new_state) {

  }

  void RTCPeerConnection::OnIceCandidate(const webrtc::IceCandidateInterface *candidate) {

  }

  void RTCPeerConnection::OnIceCandidateError(const std::string &host_candidate, const std::string &url, int error_code,
                                              const std::string &error_text) {

  }

  void RTCPeerConnection::OnRenegotiationNeeded() {

  }

  void RTCPeerConnection::OnDataChannel(rtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) {

  }

  void RTCPeerConnection::OnAddStream(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnRemoveStream(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnAddTrack(rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                                     const std::vector<rtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) {

  }

  void RTCPeerConnection::OnTrack(rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {

  }

} // namespace python_webrtc
