//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"
#include "../utils/gil.h"

#include "peer_connection_factory.h"
#include "create_session_description_observer.h"
#include "set_session_description_observer.h"

namespace python_webrtc {

  RTCPeerConnection::RTCPeerConnection() : _factory(PeerConnectionFactory::GetOrCreateDefault()) {
//    TODO get from python
    auto configuration = webrtc::PeerConnectionInterface::RTCConfiguration();
    configuration.sdp_semantics = webrtc::SdpSemantics::kUnifiedPlan;

//    TODO get port range from configurator.
//    create some struct with min and max uint16_t fields. bind it to python
    configuration.port_allocator_config.min_port = 0;
    configuration.port_allocator_config.max_port = 65535;

    webrtc::PeerConnectionDependencies dependencies(this);

    auto result = _factory->factory()->CreatePeerConnectionOrError(
        configuration, std::move(dependencies));

    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    _jinglePeerConnection = result.MoveValue();
  }

  RTCPeerConnection::~RTCPeerConnection() {
    // destroying the peer connection blocks on the signaling thread, which may be waiting for the GIL
    gil_release_if_held release;

    // closing stops the connection from calling this observer
    Close();
    // TODO data channels
//    _channels.clear();
  }

  template<typename T, typename U>
  std::shared_ptr<T> RTCPeerConnection::Wrap(Wrappers<T, U> &wrappers, webrtc::scoped_refptr<U> object) {
    std::lock_guard<std::mutex> lock(_wrappersMutex);
    auto it = wrappers.find(object.get());
    if (it != wrappers.end()) {
      return it->second;
    }

    auto wrapper = T::holder().GetOrCreate(_factory, object);
    wrappers[object.get()] = wrapper;
    return wrapper;
  }

  template<typename T, typename U>
  std::vector<std::shared_ptr<T>> RTCPeerConnection::Sync(
      Wrappers<T, U> &wrappers, const std::vector<webrtc::scoped_refptr<U>> &objects) {
    std::vector<std::shared_ptr<T>> result;
    Wrappers<T, U> current;
    {
      std::lock_guard<std::mutex> lock(_wrappersMutex);
      for (const auto &object: objects) {
        auto it = wrappers.find(object.get());
        auto wrapper = it != wrappers.end() ? it->second : T::holder().GetOrCreate(_factory, object);
        current[object.get()] = wrapper;
        result.push_back(std::move(wrapper));
      }
      std::swap(wrappers, current);
    }
    // wrappers of the objects that are gone are released here, out of the lock
    return result;
  }

  void RTCPeerConnection::ReleaseWrappers() {
    decltype(_transceivers) transceivers;
    decltype(_senders) senders;
    decltype(_receivers) receivers;
    decltype(_sctp) sctp;
    {
      std::lock_guard<std::mutex> lock(_wrappersMutex);
      std::swap(transceivers, _transceivers);
      std::swap(senders, _senders);
      std::swap(receivers, _receivers);
      std::swap(sctp, _sctp);
    }
    // released out of the lock, objects still referenced from Python stay alive
  }

  void RTCPeerConnection::Init(pybind11::module &m) {
    pybind11::class_<RTCPeerConnection, std::shared_ptr<RTCPeerConnection>>(m, "RTCPeerConnection")
        .def(pybind11::init<>(), nogil())
        .def("createOffer", &RTCPeerConnection::CreateOffer, nogil())
        .def("createAnswer", &RTCPeerConnection::CreateAnswer, nogil())
        .def("setLocalDescription", &RTCPeerConnection::SetLocalDescription, nogil())
        .def("setRemoteDescription", &RTCPeerConnection::SetRemoteDescription, nogil())
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>>(
                 &RTCPeerConnection::AddTrack), nogil())
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, const std::vector<MediaStream *> &>(
                 &RTCPeerConnection::AddTrack), nogil())
        .def("addTransceiver",
             pybind11::overload_cast<webrtc::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), nogil())
        .def("addTransceiver",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), nogil())
        .def("getTransceivers", &RTCPeerConnection::GetTransceivers, nogil())
        .def("getSenders", &RTCPeerConnection::GetSenders, nogil())
        .def("getReceivers", &RTCPeerConnection::GetReceivers, nogil())
        .def_property_readonly("sctp", nogil_fn(&RTCPeerConnection::GetSctp))
        .def("restartIce", &RTCPeerConnection::RestartIce, nogil())
        .def("removeTrack", &RTCPeerConnection::RemoveTrack, nogil())
        .def("close", &RTCPeerConnection::Close, nogil())
        .def_property_readonly("connectionState", nogil_fn(&RTCPeerConnection::GetConnectionState))
        .def_property_readonly("signalingState", nogil_fn(&RTCPeerConnection::GetSignalingState))
        .def_property_readonly("iceConnectionState", nogil_fn(&RTCPeerConnection::GetIceConnectionState))
        .def_property_readonly("iceGatheringState", nogil_fn(&RTCPeerConnection::GetIceGatheringState))
        .def_property_readonly("localDescription", nogil_fn(&RTCPeerConnection::GetLocalDescription))
        .def_property_readonly("remoteDescription", nogil_fn(&RTCPeerConnection::GetRemoteDescription));
  }

  void RTCPeerConnection::SaveLastSdp(const RTCSessionDescriptionInit &lastSdp) {
    _lastSdp = lastSdp;
  }

  void RTCPeerConnection::CreateOffer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure) {
    auto pc = connection();
    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'createOffer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."
      ));
      return;
    }

    auto observer = new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), onSuccess, onFailure);

//     TODO bind RTCOfferOptions (voice_activity_detection, iceRestart, offerToReceiveAudio, offerToReceiveVideo)
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
//    options.offer_to_receive_audio = 1;
//    options.offer_to_receive_video = 0;

    pc->CreateOffer(observer, options);
  }

  void RTCPeerConnection::CreateAnswer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure) {
    auto pc = connection();
    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'createAnswer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), onSuccess, onFailure);
//       TODO bind RTCAnswerOptions (voice_activity_detection)
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    pc->CreateAnswer(observer, options);
  }

  void RTCPeerConnection::SetLocalDescription(
      std::function<void()> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure,
      RTCSessionDescription &description) {
    auto pc = connection();
//    TODO accept RTCSessionDescriptionInit too
    if (description.getSdp().empty()) {
//      TODO use lastSdp
      _lastSdp.sdp;
    }

    auto *raw_description = static_cast<webrtc::SessionDescriptionInterface *>(description);
    std::unique_ptr<webrtc::SessionDescriptionInterface> raw_description_ptr(raw_description);

    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new webrtc::RefCountedObject<SetSessionDescriptionObserver>(onSuccess, onFailure);
    pc->SetLocalDescription(observer, raw_description_ptr.release());
  }

  void RTCPeerConnection::SetRemoteDescription(
      std::function<void()> &onSuccess,
      std::function<void(CallbackPythonWebRTCException)> &onFailure,
      RTCSessionDescription &description) {
    auto pc = connection();
//    TODO accept RTCSessionDescriptionInit too

    auto *raw_description = static_cast<webrtc::SessionDescriptionInterface *>(description);
    std::unique_ptr<webrtc::SessionDescriptionInterface> raw_description_ptr(raw_description);

    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(CallbackPythonWebRTCException(
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new webrtc::RefCountedObject<SetSessionDescriptionObserver>(onSuccess, onFailure);
    pc->SetRemoteDescription(observer, raw_description_ptr.release());
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, const std::vector<MediaStream *> &mediaStreams) {
    auto pc = connection();
    if (!pc) {
      throw PythonWebRTCException("Cannot add track; RTCPeerConnection is closed");
    }

    std::vector<std::string> streamIds;
    streamIds.reserve(mediaStreams.size());
    for (auto const &stream: mediaStreams) {
      streamIds.emplace_back(stream->stream()->id());
    }

    auto result = pc->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    auto rtpSender = result.value();
    return Wrap(_senders, rtpSender);
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, std::optional<std::reference_wrapper<MediaStream>> mediaStream) {
    auto pc = connection();
    if (!pc) {
      throw PythonWebRTCException("Cannot add track; RTCPeerConnection is closed");
    }

    std::vector<std::string> streamIds;
    if (mediaStream != std::nullopt) {
      streamIds.emplace_back(mediaStream->get().stream()->id());
    }

    auto result = pc->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    auto rtpSender = result.value();
    return Wrap(_senders, rtpSender);
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      webrtc::MediaType kind, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    auto pc = connection();
    if (!pc) {
      throw PythonWebRTCException("Cannot add transceiver; RTCPeerConnection is closed");
    } else if (pc->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  pc->AddTransceiver(kind, init->get()) :
                  pc->AddTransceiver(kind);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    return Wrap(_transceivers, result.value());
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      MediaStreamTrack &track, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    auto pc = connection();
    if (!pc) {
      throw PythonWebRTCException("Cannot add transceiver; RTCPeerConnection is closed");
    } else if (pc->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  pc->AddTransceiver(track.track(), init->get()) :
                  pc->AddTransceiver(track.track());
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    return Wrap(_transceivers, result.value());
  }

  std::vector<std::shared_ptr<RTCRtpTransceiver>> RTCPeerConnection::GetTransceivers() {
    auto pc = connection();
    if (pc && pc->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan) {
      return Sync(_transceivers, pc->GetTransceivers());
    }

    return {};
  }

  std::vector<std::shared_ptr<RTCRtpSender>> RTCPeerConnection::GetSenders() {
    auto pc = connection();
    if (pc) {
      return Sync(_senders, pc->GetSenders());
    }

    return {};
  }

  std::vector<std::shared_ptr<RTCRtpReceiver>> RTCPeerConnection::GetReceivers() {
    auto pc = connection();
    if (pc) {
      return Sync(_receivers, pc->GetReceivers());
    }

    return {};
  }

  std::optional<std::shared_ptr<RTCSctpTransport>> RTCPeerConnection::GetSctp() {
    auto pc = connection();
    auto transport = pc ? pc->GetSctpTransport() : nullptr;
    if (!transport) {
      return {};
    }

    std::shared_ptr<RTCSctpTransport> previous;
    std::lock_guard<std::mutex> lock(_wrappersMutex);
    if (!_sctp || _sctp->transport() != transport) {
      previous = std::move(_sctp);
      _sctp = RTCSctpTransport::holder().GetOrCreate(_factory, transport);
    }
    return _sctp;
  }

  void RTCPeerConnection::RestartIce() {
    auto pc = connection();
    if (pc) {
      pc->RestartIce();
    }
  }

  void RTCPeerConnection::RemoveTrack(RTCRtpSender &sender) {
    auto pc = connection();
    if (!pc) {
      throw PythonWebRTCException("Cannot remove track; RTCPeerConnection is closed");
    }

    auto senders = pc->GetSenders();
    if (std::find(senders.begin(), senders.end(), sender.sender()) == senders.end()) {
      throw PythonWebRTCException("Cannot remove track because sender not found in senders of PeerConnection");
    }

    auto error = pc->RemoveTrackOrError(sender.sender());
    if (!error.ok()) {
      throw wrapRTCError(error);
    }
  }

  void RTCPeerConnection::Close() {
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> pc;
    {
      std::lock_guard<std::mutex> lock(_connectionMutex);
      pc = std::move(_jinglePeerConnection);
    }

    if (pc) {
      pc->Close();

      if (pc->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan) {
        for (const auto &transceiver: pc->GetTransceivers()) {
          Wrap(_transceivers, transceiver)->GetReceiver()->GetTrack()->OnPeerConnectionClosed();
        }
      }
    }

    // wrappers still referenced from Python keep their (closed) state
    ReleaseWrappers();
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::connection() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _jinglePeerConnection;
  }

  std::optional<RTCSessionDescription> RTCPeerConnection::GetDescription(bool local) {
    auto pc = connection();
    if (!pc) {
      return std::nullopt;
    }

    // the description is owned by the peer connection and must be read on the signaling thread
    std::optional<RTCSessionDescriptionInit> init;
    _factory->_signalingThread->BlockingCall([&]() {
      auto description = local ? pc->local_description()
                               : pc->remote_description();
      if (description) {
        init = RTCSessionDescriptionInit::Wrap(const_cast<webrtc::SessionDescriptionInterface *>(description));
      }
    });

    if (!init) {
      return std::nullopt;
    }
    return RTCSessionDescription(*init);
  }

  std::optional<RTCSessionDescription> RTCPeerConnection::GetLocalDescription() {
    return GetDescription(true);
  }

  std::optional<RTCSessionDescription> RTCPeerConnection::GetRemoteDescription() {
    return GetDescription(false);
  }

  webrtc::PeerConnectionInterface::PeerConnectionState RTCPeerConnection::GetConnectionState() {
    auto pc = connection();
    if (pc) {
      return pc->peer_connection_state();
    } else {
      return webrtc::PeerConnectionInterface::PeerConnectionState::kClosed;
    }
  }

  webrtc::PeerConnectionInterface::SignalingState RTCPeerConnection::GetSignalingState() {
    auto pc = connection();
    if (pc) {
      return pc->signaling_state();
    } else {
      return webrtc::PeerConnectionInterface::SignalingState::kClosed;
    }
  }

  webrtc::PeerConnectionInterface::IceConnectionState RTCPeerConnection::GetIceConnectionState() {
    auto pc = connection();
    if (pc) {
      return pc->standardized_ice_connection_state();
    } else {
      return webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionClosed;
    }
  }

  webrtc::PeerConnectionInterface::IceGatheringState RTCPeerConnection::GetIceGatheringState() {
    auto pc = connection();
    if (pc) {
      return pc->ice_gathering_state();
    } else {
      return webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringComplete;
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

  void RTCPeerConnection::OnIceCandidateError(const std::string &address, int port, const std::string &url, int error_code,
                                              const std::string &error_text) {

  }

  void RTCPeerConnection::OnRenegotiationNeeded() {

  }

  void RTCPeerConnection::OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) {

  }

  void RTCPeerConnection::OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                                     const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) {

  }

  void RTCPeerConnection::OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {

  }

} // namespace python_webrtc
