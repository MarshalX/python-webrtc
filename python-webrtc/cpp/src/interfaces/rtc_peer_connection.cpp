//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"

#include <webrtc/p2p/client/basic_port_allocator.h>

#include "peer_connection_factory.h"
#include "create_session_description_observer.h"
#include "set_session_description_observer.h"

namespace python_webrtc {

  RTCPeerConnection::RTCPeerConnection() {
    _factory = PeerConnectionFactory::GetOrCreateDefault();
    _shouldReleaseFactory = true;

//    TODO get from python
    auto configuration = webrtc::PeerConnectionInterface::RTCConfiguration();
    configuration.sdp_semantics = webrtc::SdpSemantics::kUnifiedPlan;

    auto portAllocator = std::unique_ptr<cricket::PortAllocator>(new cricket::BasicPortAllocator(
        _factory->getNetworkManager(),
        _factory->getSocketFactory())
    );

//    TODO get and set port range from configurator.
//    create some struct with min and max uint16_t fields. bind it to python
//    _port_range =  configurator (with additional fields)...port_range

    portAllocator->SetPortRange(0, 65535); // TODO get from config or default

    webrtc::PeerConnectionDependencies dependencies(this);
    dependencies.allocator = std::move(portAllocator);

    auto result = _factory->factory()->CreatePeerConnectionOrError(
        configuration, std::move(dependencies));

    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    _jinglePeerConnection = result.MoveValue();
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
        .def("createOffer", &RTCPeerConnection::CreateOffer)
        .def("createAnswer", &RTCPeerConnection::CreateAnswer)
        .def("setLocalDescription", &RTCPeerConnection::SetLocalDescription)
        .def("setRemoteDescription", &RTCPeerConnection::SetRemoteDescription)
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>>(
                 &RTCPeerConnection::AddTrack), pybind11::return_value_policy::reference)
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, const std::vector<MediaStream *> &>(
                 &RTCPeerConnection::AddTrack), pybind11::return_value_policy::reference)
        .def("addTransceiver",
             pybind11::overload_cast<cricket::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), pybind11::return_value_policy::reference)
        .def("addTransceiver",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), pybind11::return_value_policy::reference)
        .def("getTransceivers", &RTCPeerConnection::GetTransceivers)
        .def("getSenders", &RTCPeerConnection::GetSenders)
        .def("getReceivers", &RTCPeerConnection::GetReceivers)
        .def("close", &RTCPeerConnection::Close);
  }

  void RTCPeerConnection::SaveLastSdp(const RTCSessionDescriptionInit &lastSdp) {
    _lastSdp = lastSdp;
  }

  void RTCPeerConnection::CreateOffer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure) {
    if (!_jinglePeerConnection ||
        _jinglePeerConnection->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'createOffer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."
      ));
      return;
    }

    auto observer = new rtc::RefCountedObject<CreateSessionDescriptionObserver>(this, onSuccess, onFailure);

//     TODO bind RTCOfferOptions (voice_activity_detection, iceRestart, offerToReceiveAudio, offerToReceiveVideo)
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    options.offer_to_receive_audio = 1;
    options.offer_to_receive_video = 0;

    _jinglePeerConnection->CreateOffer(observer, options);
  }

  void RTCPeerConnection::CreateAnswer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure) {
    if (!_jinglePeerConnection ||
        _jinglePeerConnection->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'createAnswer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new rtc::RefCountedObject<CreateSessionDescriptionObserver>(this, onSuccess, onFailure);
//       TODO bind RTCAnswerOptions (voice_activity_detection)
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    _jinglePeerConnection->CreateAnswer(observer, options);
  }

  void RTCPeerConnection::SetLocalDescription(
      std::function<void()> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure,
      RTCSessionDescription &description) {
//    TODO accept RTCSessionDescriptionInit too
    if (description.getSdp().empty()) {
//      TODO use lastSdp
      _lastSdp.sdp;
    }

    auto *raw_description = static_cast<webrtc::SessionDescriptionInterface *>(description);
    std::unique_ptr<webrtc::SessionDescriptionInterface> raw_description_ptr(raw_description);

    if (!_jinglePeerConnection ||
        _jinglePeerConnection->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new rtc::RefCountedObject<SetSessionDescriptionObserver>(onSuccess, onFailure);
    _jinglePeerConnection->SetLocalDescription(observer, raw_description_ptr.release());
  }

  void RTCPeerConnection::SetRemoteDescription(
      std::function<void()> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure,
      RTCSessionDescription &description) {
//    TODO accept RTCSessionDescriptionInit too

    auto *raw_description = static_cast<webrtc::SessionDescriptionInterface *>(description);
    std::unique_ptr<webrtc::SessionDescriptionInterface> raw_description_ptr(raw_description);

    if (!_jinglePeerConnection ||
        _jinglePeerConnection->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new rtc::RefCountedObject<SetSessionDescriptionObserver>(onSuccess, onFailure);
    _jinglePeerConnection->SetRemoteDescription(observer, raw_description_ptr.release());
  }

  RTCRtpSender *RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, const std::vector<MediaStream *> &mediaStreams) {
    if (!_jinglePeerConnection) {
      throw PythonWebRTCException("Cannot add track; RTCPeerConnection is closed");
    }

    std::vector<std::string> streamIds;
    streamIds.reserve(mediaStreams.size());
    for (auto const &stream: mediaStreams) {
      streamIds.emplace_back(stream->stream()->id());
    }

    auto result = _jinglePeerConnection->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    auto rtpSender = result.value();
    return RTCRtpSender::holder()->GetOrCreate(_factory, rtpSender);
  }

  RTCRtpSender *RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, std::optional<std::reference_wrapper<MediaStream>> mediaStream) {
    if (!_jinglePeerConnection) {
      throw PythonWebRTCException("Cannot add track; RTCPeerConnection is closed");
    }

    std::vector<std::string> streamIds;
    if (mediaStream != std::nullopt) {
      streamIds.emplace_back(mediaStream->get().stream()->id());
    }

    auto result = _jinglePeerConnection->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    auto rtpSender = result.value();
    return RTCRtpSender::holder()->GetOrCreate(_factory, rtpSender);
  }

  RTCRtpTransceiver *RTCPeerConnection::AddTransceiver(
      cricket::MediaType kind, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    if (!_jinglePeerConnection) {
      throw PythonWebRTCException("Cannot add transceiver; RTCPeerConnection is closed");
    } else if (_jinglePeerConnection->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  _jinglePeerConnection->AddTransceiver(kind, init->get()) :
                  _jinglePeerConnection->AddTransceiver(kind);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    return RTCRtpTransceiver::holder()->GetOrCreate(_factory, result.value());
  }

  RTCRtpTransceiver *RTCPeerConnection::AddTransceiver(
      MediaStreamTrack &track, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    if (!_jinglePeerConnection) {
      throw PythonWebRTCException("Cannot add transceiver; RTCPeerConnection is closed");
    } else if (_jinglePeerConnection->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  _jinglePeerConnection->AddTransceiver(track.track(), init->get()) :
                  _jinglePeerConnection->AddTransceiver(track.track());
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    return RTCRtpTransceiver::holder()->GetOrCreate(_factory, result.value());
  }

  std::vector<RTCRtpTransceiver *> RTCPeerConnection::GetTransceivers() {
    std::vector<RTCRtpTransceiver *> transceivers;

    auto isUnified = _jinglePeerConnection->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan;
    if (_jinglePeerConnection && isUnified) {
      for (const auto &transceiver: _jinglePeerConnection->GetTransceivers()) {
        transceivers.emplace_back(RTCRtpTransceiver::holder()->GetOrCreate(_factory, transceiver));
      }
    }

    return transceivers;
  }

  std::vector<RTCRtpSender *> RTCPeerConnection::GetSenders() {
    std::vector<RTCRtpSender *> senders;

    if (_jinglePeerConnection) {
      for (const auto &sender: _jinglePeerConnection->GetSenders()) {
        senders.emplace_back(RTCRtpSender::holder()->GetOrCreate(_factory, sender));
      }
    }

    return senders;
  }

  std::vector<RTCRtpReceiver *> RTCPeerConnection::GetReceivers() {
    std::vector<RTCRtpReceiver *> receivers;

    if (_jinglePeerConnection) {
      for (const auto &receiver: _jinglePeerConnection->GetReceivers()) {
        receivers.emplace_back(RTCRtpReceiver::holder()->GetOrCreate(_factory, receiver));
      }
    }

    return receivers;
  }

  void RTCPeerConnection::Close() {
    if (_jinglePeerConnection) {
      _jinglePeerConnection->Close();

      if (_jinglePeerConnection->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan) {
        for (const auto &transceiver: _jinglePeerConnection->GetTransceivers()) {
          auto track = MediaStreamTrack::holder()->GetOrCreate(_factory, transceiver->receiver()->track());
          track->OnPeerConnectionClosed();
        }
      }
    }

    _jinglePeerConnection = nullptr;

    if (_factory) {
      if (_shouldReleaseFactory) {
        PeerConnectionFactory::Release();
      }
      _factory = nullptr;
    }
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
