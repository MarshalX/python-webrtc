//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"
#include "../../utils/python_callback.h"

#include <algorithm>
#include <limits>
#include <utility>

#include <pc/rtp_media_utils.h>
#include <pc/session_description.h>

#include "../../utils/gil.h"
#include "../../utils/libwebrtc_thread.h"
#include "../peer_connection_factory.h"

namespace python_webrtc {

  // what libwebrtc offers in its descriptions, and assumes without a max-message-size (RFC 8841)
  static constexpr double kLocalMaxMessageSize = 256 * 1024;
  static constexpr double kDefaultRemoteMaxMessageSize = 65536;

  RTCPeerConnection::RTCPeerConnection(const std::optional<ConfigurationInit> &init)
      : _factory(PeerConnectionFactory::GetOrCreateDefault()), _configuration(init.value_or(ConfigurationInit())) {
    auto configuration = webrtc::PeerConnectionInterface::RTCConfiguration();
    configuration.sdp_semantics = webrtc::SdpSemantics::kUnifiedPlan;
    configuration = _configuration.Apply(configuration);

    webrtc::PeerConnectionDependencies dependencies(this);

    auto result = _factory->factory()->CreatePeerConnectionOrError(configuration, std::move(dependencies));

    if (!result.ok()) {
      throw RTCException(result.error());
    }

    _jinglePeerConnection = result.MoveValue();
  }

  RTCPeerConnection::~RTCPeerConnection() {
    // destroying the peer connection blocks on the signaling thread, which may be waiting for the GIL
    const BlockingDestructor release("RTCPeerConnection");

    // closing stops the connection from calling this observer
    Close();

    // released here, without the GIL, as it blocks on the signaling thread
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> closed;
    {
      const TrackedLock lock(_connectionMutex);
      closed = std::move(_closedConnection);
    }
    closed = nullptr;
    DropListeners();
  }

  void RTCPeerConnection::Init(pybind11::module &m) {
    Listeners::BindClass<RTCPeerConnection>(m, "RTCPeerConnection")
        .def(pybind11::init(nogil_factory(+[](const std::optional<ConfigurationInit> &configuration) {
               return std::shared_ptr<RTCPeerConnection>(new RTCPeerConnection(configuration),
                                                         DeleteOffLibwebrtcThread());
             })),
             pybind11::arg("configuration"))
        .def("createOffer", WithCallbacks(&RTCPeerConnection::CreateOffer), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"), pybind11::arg("iceRestart"))
        .def("createAnswer", WithCallbacks(&RTCPeerConnection::CreateAnswer), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"))
        .def("setLocalDescription", WithCallbacks(&RTCPeerConnection::SetLocalDescription), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"), pybind11::arg("description"))
        .def("setRemoteDescription", WithCallbacks(&RTCPeerConnection::SetRemoteDescription),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("description"))
        .def("addIceCandidate", WithCallbacks(&RTCPeerConnection::AddIceCandidate), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"), pybind11::arg("candidate"), pybind11::arg("sdpMid"),
             pybind11::arg("sdpMLineIndex"), pybind11::arg("usernameFragment"))
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>>(
                 &RTCPeerConnection::AddTrack),
             nogil(), pybind11::arg("track"), pybind11::arg("stream"))
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, const std::vector<MediaStream *> &>(
                 &RTCPeerConnection::AddTrack),
             nogil(), pybind11::arg("track"), pybind11::arg("streams"))
        .def("removeTrack", &RTCPeerConnection::RemoveTrack, nogil(), pybind11::arg("sender"))
        .def("addTransceiver",
             pybind11::overload_cast<webrtc::MediaType,
                                     std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver),
             nogil(), pybind11::arg("kind"), pybind11::arg("init"))
        .def("addTransceiver",
             pybind11::overload_cast<MediaStreamTrack &,
                                     std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver),
             nogil(), pybind11::arg("track"), pybind11::arg("init"))
        .def("getTransceivers", &RTCPeerConnection::GetTransceivers, nogil())
        .def("getSenders", &RTCPeerConnection::GetSenders, nogil())
        .def("getReceivers", &RTCPeerConnection::GetReceivers, nogil())
        .def("createDataChannel", &RTCPeerConnection::CreateDataChannel, nogil(), pybind11::arg("label"),
             pybind11::arg("ordered"), pybind11::arg("maxPacketLifeTime"), pybind11::arg("maxRetransmits"),
             pybind11::arg("protocol"), pybind11::arg("negotiated"), pybind11::arg("id"), pybind11::arg("priority"))
        .def("getStats", WithCallbacks(&RTCPeerConnection::GetStats), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"))
        .def("restartIce", &RTCPeerConnection::RestartIce, nogil())
        .def("getConfiguration", &RTCPeerConnection::GetConfiguration, nogil())
        .def("setConfiguration", &RTCPeerConnection::SetConfiguration, nogil(), pybind11::arg("configuration"))
        .def("close", &RTCPeerConnection::Close, nogil())
        .def_property_readonly("sctp", nogil_fn(&RTCPeerConnection::GetSctp))
        .def_property_readonly("connectionState", nogil_fn(&RTCPeerConnection::GetConnectionState))
        .def_property_readonly("signalingState", nogil_fn(&RTCPeerConnection::GetSignalingState))
        .def_property_readonly("iceConnectionState", nogil_fn(&RTCPeerConnection::GetIceConnectionState))
        .def_property_readonly("iceGatheringState", nogil_fn(&RTCPeerConnection::GetIceGatheringState))
        .def_property_readonly("localDescription", nogil_fn(&RTCPeerConnection::GetLocalDescription))
        .def_property_readonly("remoteDescription", nogil_fn(&RTCPeerConnection::GetRemoteDescription))
        .def_property_readonly("currentLocalDescription", nogil_fn(&RTCPeerConnection::GetCurrentLocalDescription))
        .def_property_readonly("currentRemoteDescription", nogil_fn(&RTCPeerConnection::GetCurrentRemoteDescription))
        .def_property_readonly("pendingLocalDescription", nogil_fn(&RTCPeerConnection::GetPendingLocalDescription))
        .def_property_readonly("pendingRemoteDescription", nogil_fn(&RTCPeerConnection::GetPendingRemoteDescription))
        .def_property_readonly("canTrickleIceCandidates", nogil_fn(&RTCPeerConnection::GetCanTrickleIceCandidates))
        .def("_shouldFireNegotiationNeededEvent", &RTCPeerConnection::ShouldFireNegotiationNeededEvent, nogil(),
             pybind11::arg("eventId"))
        .def("_surfaceSignalingState", &RTCPeerConnection::SurfaceSignalingState, nogil(), pybind11::arg("state"))
        .def("_surfaceIceConnectionState", &RTCPeerConnection::SurfaceIceConnectionState, nogil(),
             pybind11::arg("state"))
        .def("_surfaceIceGatheringState", &RTCPeerConnection::SurfaceIceGatheringState, nogil(), pybind11::arg("state"))
        .def("_surfaceConnectionState", &RTCPeerConnection::SurfaceConnectionState, nogil(), pybind11::arg("state"))
        .def("_refreshDescriptions", &RTCPeerConnection::RefreshDescriptions, nogil())
        .def_static("_connectionOf", &RTCPeerConnection::ConnectionOf, nogil(), pybind11::arg("sender"))
        .def("_applyDescriptions", &RTCPeerConnection::ApplyDescriptions, nogil(),
             pybind11::arg("snapshot") = std::nullopt);
  }

  void RTCPeerConnection::ReleaseElsewhere(std::shared_ptr<RTCPeerConnection> &&connection) {
    if (connection) {
      ReleaseThread::Post([connection = std::move(connection)]() mutable { connection = nullptr; });
    }
  }

  std::optional<std::shared_ptr<RTCPeerConnection>> RTCPeerConnection::ConnectionOf(RTCRtpSender &sender) {
    if (auto connection = sender.GetConnection()) {
      return connection;
    }
    return std::nullopt;
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::connection() {
    const TrackedLock lock(_connectionMutex);
    return _jinglePeerConnection;
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::closedConnection() {
    const TrackedLock lock(_connectionMutex);
    return _closedConnection;
  }

  bool RTCPeerConnection::IsClosed() {
    return !connection();
  }

  template <typename T, typename U>
  std::shared_ptr<T> RTCPeerConnection::Wrap(Wrappers<T, U> &wrappers, webrtc::scoped_refptr<U> object) {
    if (!OnLibwebrtcThread()) {
      // on the signaling thread, which wraps objects too: the lock isn't held while waiting for it
      const gil_release_if_held release;
      return BlockingCallOn(_factory->signalingThread(), [&]() { return Wrap(wrappers, std::move(object)); });
    }
    std::shared_ptr<T> wrapper;
    {
      const TrackedLock lock(_wrappersMutex);
      auto it = wrappers.find(object.get());
      if (it != wrappers.end()) {
        return it->second;
      }

      wrapper = T::holder().GetOrCreate(_factory, object);
      wrappers[object.get()] = wrapper;
    }
    Adopt(wrapper);
    return wrapper;
  }

  template <typename T, typename U>
  std::vector<std::shared_ptr<T>> RTCPeerConnection::Sync(Wrappers<T, U> &wrappers,
                                                          const std::vector<webrtc::scoped_refptr<U>> &objects) {
    if (!OnLibwebrtcThread()) {
      // see Wrap
      const gil_release_if_held release;
      return BlockingCallOn(_factory->signalingThread(), [&]() { return Sync(wrappers, objects); });
    }
    std::vector<std::shared_ptr<T>> result;
    Wrappers<T, U> current;
    {
      const TrackedLock lock(_wrappersMutex);
      for (const auto &object : objects) {
        auto it = wrappers.find(object.get());
        auto wrapper = it != wrappers.end() ? it->second : T::holder().GetOrCreate(_factory, object);
        current[object.get()] = wrapper;
        result.push_back(std::move(wrapper));
      }
      std::swap(wrappers, current);
    }
    for (const auto &wrapper : result) {
      Adopt(wrapper);
    }
    // wrappers of the objects that are gone are released here, out of the lock
    return result;
  }

  template <typename T, typename U>
  std::vector<std::shared_ptr<T>> RTCPeerConnection::Unkept(const std::vector<webrtc::scoped_refptr<U>> &objects) {
    std::vector<std::shared_ptr<T>> result;
    for (const auto &object : objects) {
      auto wrapper = T::holder().GetOrCreate(_factory, object);
      Adopt(wrapper);
      result.push_back(std::move(wrapper));
    }
    return result;
  }

  void RTCPeerConnection::ReleaseWrappers() {
    decltype(_transceivers) transceivers;
    decltype(_senders) senders;
    decltype(_receivers) receivers;
    decltype(_sctp) sctp;
    decltype(_channels) channels;
    decltype(_dtlsTransports) dtlsTransports;
    {
      const TrackedLock lock(_wrappersMutex);
      std::swap(channels, _channels);
      std::swap(dtlsTransports, _dtlsTransports);
      std::swap(transceivers, _transceivers);
      std::swap(senders, _senders);
      std::swap(receivers, _receivers);
      std::swap(sctp, _sctp);
    }
    // released out of the lock, objects still referenced from Python stay alive
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpSender> &sender) {
    sender->SetConnection(weak_from_this());
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpReceiver> &receiver) {
    receiver->SetConnection(weak_from_this());
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpTransceiver> &transceiver) {
    transceiver->SetConnection(weak_from_this());
    Adopt(transceiver->GetSender());
    Adopt(transceiver->GetReceiver());
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCDataChannel> &channel) {
    channel->SetMaxMessageSizeGetter([weak = weak_from_this()]() -> std::optional<double> {
      auto self = weak.lock();
      auto sctp = self ? self->GetSctp() : std::nullopt;
      return sctp ? (*sctp)->GetMaxMessageSize() : std::nullopt;
    });
    channel->SetClosedCallback([weak = weak_from_this(), key = channel->channel().get()]() {
      if (auto self = weak.lock()) {
        self->ForgetChannel(key);
      }
    });
  }

  void RTCPeerConnection::ForgetChannel(webrtc::DataChannelInterface *channel) {
    std::shared_ptr<RTCDataChannel> forgotten;
    {
      const TrackedLock lock(_wrappersMutex);
      auto it = _channels.find(channel);
      if (it == _channels.end()) {
        return;
      }
      forgotten = std::move(it->second);
      _channels.erase(it);
    }
    // released out of the lock
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCSctpTransport> &sctp) {
    sctp->SetMaxMessageSizeGetter([weak = weak_from_this()]() -> std::optional<double> {
      auto self = weak.lock();
      return self ? self->MaxMessageSize() : std::nullopt;
    });
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCDtlsTransport> &dtls) {
    auto iceTransport = dtls->transport()->ice_transport();
    dtls->GetIceTransport()->SetParametersGetter([weak = weak_from_this(), iceTransport](bool local) {
      auto self = weak.lock();
      return self ? self->IceParameters(iceTransport.get(), local) : std::nullopt;
    });
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(MediaStreamTrack &mediaStreamTrack,
                                                            const std::vector<MediaStream *> &mediaStreams) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("addTrack"));
    }

    std::vector<std::string> streamIds;
    streamIds.reserve(mediaStreams.size());
    for (const auto &stream : mediaStreams) {
      streamIds.emplace_back(stream->stream()->id());
    }

    auto result = pc->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw RTCException(result.error());
    }

    QueueNegotiationNeeded();
    return Wrap(_senders, result.value());
  }

  std::shared_ptr<RTCRtpSender>
  RTCPeerConnection::AddTrack(MediaStreamTrack &mediaStreamTrack,
                              std::optional<std::reference_wrapper<MediaStream>> mediaStream) {
    std::vector<MediaStream *> mediaStreams;
    if (mediaStream) {
      mediaStreams.push_back(&mediaStream->get());
    }
    return AddTrack(mediaStreamTrack, mediaStreams);
  }

  void RTCPeerConnection::RemoveTrack(RTCRtpSender &sender) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("removeTrack"));
    }

    if (sender.GetConnection().get() != this) {
      throw RTCException(webrtc::RTCErrorType::INVALID_PARAMETER,
                         "The sender was not created by this RTCPeerConnection");
    }
    // stopped or rolled back: a no-op
    auto transceivers = pc->GetTransceivers();
    auto transceiver = std::ranges::find_if(
        transceivers, [&](const auto &candidate) { return candidate->sender() == sender.sender(); });
    if (transceiver != transceivers.end() && ((*transceiver)->stopping() || (*transceiver)->stopped())) {
      return;
    }
    auto senders = pc->GetSenders();
    if (std::ranges::find(senders, sender.sender()) == senders.end()) {
      return;
    }

    auto error = pc->RemoveTrackOrError(sender.sender());
    if (!error.ok()) {
      throw RTCException(error);
    }
    QueueNegotiationNeeded();
  }

  std::shared_ptr<RTCRtpTransceiver>
  RTCPeerConnection::AddTransceiver(webrtc::MediaType kind,
                                    std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("addTransceiver"));
    }
    return AddedTransceiver(init ? pc->AddTransceiver(kind, init->get()) : pc->AddTransceiver(kind));
  }

  std::shared_ptr<RTCRtpTransceiver>
  RTCPeerConnection::AddTransceiver(MediaStreamTrack &track,
                                    std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("addTransceiver"));
    }
    return AddedTransceiver(init ? pc->AddTransceiver(track.track(), init->get()) : pc->AddTransceiver(track.track()));
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddedTransceiver(
      webrtc::RTCErrorOr<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>> result) {
    if (!result.ok()) {
      throw RTCException(result.error());
    }
    QueueNegotiationNeeded();
    return Wrap(_transceivers, result.value());
  }

  std::vector<std::shared_ptr<RTCRtpTransceiver>> RTCPeerConnection::GetTransceivers() {
    if (auto pc = connection()) {
      return Sync(_transceivers, pc->GetTransceivers());
    }
    auto closed = closedConnection();
    return closed ? Unkept<RTCRtpTransceiver>(closed->GetTransceivers())
                  : std::vector<std::shared_ptr<RTCRtpTransceiver>>();
  }

  std::vector<std::shared_ptr<RTCRtpSender>> RTCPeerConnection::GetSenders() {
    if (auto pc = connection()) {
      return Sync(_senders, pc->GetSenders());
    }
    // the transceivers of a closed connection are stopped, which leaves no senders and receivers
    return {};
  }

  std::vector<std::shared_ptr<RTCRtpReceiver>> RTCPeerConnection::GetReceivers() {
    if (auto pc = connection()) {
      return Sync(_receivers, pc->GetReceivers());
    }
    // the transceivers of a closed connection are stopped, which leaves no senders and receivers
    return {};
  }

  std::shared_ptr<RTCDataChannel>
  RTCPeerConnection::CreateDataChannel(const std::string &label, bool ordered, std::optional<int> maxPacketLifeTime,
                                       std::optional<int> maxRetransmits, const std::string &protocol, bool negotiated,
                                       std::optional<int> id, webrtc::Priority priority) {
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      throw RTCException(closedError("createDataChannel"));
    }

    webrtc::DataChannelInit init;
    init.ordered = ordered;
    init.maxRetransmitTime = maxPacketLifeTime;
    init.maxRetransmits = maxRetransmits;
    init.protocol = protocol;
    init.negotiated = negotiated;
    init.id = id.value_or(-1);
    init.priority = webrtc::PriorityValue(priority);

    auto result = pc->CreateDataChannelOrError(label, &init);
    if (!result.ok()) {
      auto error = result.MoveError();
      // an id in use, no id left, or too many channels: the arguments were checked by Python already
      throw RTCException(error.type() == webrtc::RTCErrorType::INVALID_STATE
                             ? error.type()
                             : webrtc::RTCErrorType::UNSUPPORTED_OPERATION,
                         error.message());
    }
    QueueNegotiationNeeded();
    return Wrap(_channels, result.MoveValue());
  }

  std::optional<std::shared_ptr<RTCSctpTransport>> RTCPeerConnection::GetSctp() {
    if (!OnLibwebrtcThread()) {
      // see Wrap
      const gil_release_if_held release;
      return BlockingCallOn(_factory->signalingThread(), [this]() { return GetSctp(); });
    }
    auto pc = connection();
    auto transport = pc ? pc->GetSctpTransport() : nullptr;
    if (!transport) {
      return {};
    }

    // unlocked: the constructor blocks
    auto wrapper = RTCSctpTransport::holder().GetOrCreate(_factory, transport);
    std::shared_ptr<RTCSctpTransport> previous;
    const TrackedLock lock(_wrappersMutex);
    if (_sctp != wrapper) {
      previous = std::move(_sctp);
      _sctp = std::move(wrapper);
      Adopt(_sctp);
    }
    return _sctp;
  }

  // As the specification updates the data max message size: the max-message-size of the negotiated remote
  // description (the default without it), limited by what the local side can send, where 0 means no limit
  std::optional<double> RTCPeerConnection::MaxMessageSize() {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return BlockingCallOn(_factory->signalingThread(), [&pc]() -> std::optional<double> {
      auto sctpSize = [](const webrtc::SessionDescriptionInterface *description) -> std::optional<int> {
        if (!description) {
          return {};
        }
        for (const auto &content : description->description()->contents()) {
          const auto *sctp = content.media_description() ? content.media_description()->as_sctp() : nullptr;
          if (sctp && !content.rejected) {
            return sctp->max_message_size();
          }
        }
        return {};
      };
      const double canSendSize = sctpSize(pc->current_local_description()).value_or(kLocalMaxMessageSize);
      // updated once the description is negotiated, when an answer is set
      const double remoteSize = sctpSize(pc->current_remote_description()).value_or(kDefaultRemoteMaxMessageSize);
      if (remoteSize == 0 && canSendSize == 0) {
        return std::numeric_limits<double>::infinity();
      }
      if (remoteSize == 0 || canSendSize == 0) {
        return std::max(remoteSize, canSendSize);
      }
      return std::min(remoteSize, canSendSize);
    });
  }

  ConfigurationInit RTCPeerConnection::GetConfiguration() {
    const TrackedLock lock(_connectionMutex);
    return _configuration;
  }

  void RTCPeerConnection::SetConfiguration(const ConfigurationInit &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("setConfiguration"));
    }

    {
      const TrackedLock lock(_connectionMutex);
      if (init.alwaysNegotiateDataChannels != _configuration.alwaysNegotiateDataChannels ||
          init.rtpHeaderEncryptionPolicy != _configuration.rtpHeaderEncryptionPolicy) {
        throw RTCException(webrtc::RTCErrorType::INVALID_MODIFICATION,
                           "alwaysNegotiateDataChannels and rtpHeaderEncryptionPolicy can't be changed");
      }
    }
    auto error = pc->SetConfiguration(init.Apply(pc->GetConfiguration()));
    if (!error.ok()) {
      throw RTCException(error);
    }

    const TrackedLock lock(_connectionMutex);
    auto certificates = _configuration.certificates;
    _configuration = init;
    if (!_configuration.certificates) {
      _configuration.certificates = certificates;
    }
  }

  void RTCPeerConnection::RestartIce() {
    auto pc = connection();
    // before the first local description, there are no credentials to replace: the first offer has new ones
    if (pc && (pc->local_description() != nullptr)) {
      pc->RestartIce();
      QueueNegotiationNeeded();
    }
  }

  void RTCPeerConnection::QueueNegotiationNeeded() {
    // libwebrtc posts the negotiationneeded event of a change to the signaling thread: once the thread ran it,
    // the event is queued during the call
    BlockingCallOn(_factory->signalingThread(), []() {});
  }

  bool RTCPeerConnection::ShouldFireNegotiationNeededEvent(uint32_t eventId) {
    auto pc = connection();
    return pc && pc->ShouldFireNegotiationNeededEvent(eventId);
  }

  void RTCPeerConnection::Close() {
    // closing changes states, but a closed connection fires no events, nor do its channels and transports
    Mute();
    {
      const TrackedLock lock(_wrappersMutex);
      for (auto &channel : _channels) {
        channel.second->OnPeerConnectionClosed();
      }
    }
    MuteTransports();

    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> pc;
    {
      const TrackedLock lock(_connectionMutex);
      pc = std::move(_jinglePeerConnection);
      if (pc) {
        _closedConnection = pc;
      }
    }

    if (pc) {
      pc->Close();
      for (const auto &transceiver : pc->GetTransceivers()) {
        Wrap(_transceivers, transceiver)->GetReceiver()->GetTrack()->OnPeerConnectionClosed();
        if (auto sender = RTCRtpSender::holder().Find(transceiver->sender().get())) {
          sender->ReleaseTransform();
        }
        if (auto receiver = RTCRtpReceiver::holder().Find(transceiver->receiver().get())) {
          receiver->ReleaseTransform();
        }
      }
    }

    // wrappers still referenced from Python keep their (closed) state
    ReleaseWrappers();
  }

  void RTCPeerConnection::SurfaceSignalingState(SignalingState state) {
    _surfacedSignalingState.Surface(state);
  }

  void RTCPeerConnection::SurfaceIceConnectionState(IceConnectionState state) {
    _surfacedIceConnectionState.Surface(state);
  }

  void RTCPeerConnection::SurfaceIceGatheringState(IceGatheringState state) {
    _surfacedIceGatheringState.Surface(state);
  }

  void RTCPeerConnection::SurfaceConnectionState(PeerConnectionState state) {
    _surfacedConnectionState.Surface(state);
  }

  RTCPeerConnection::PeerConnectionState RTCPeerConnection::GetConnectionState() {
    auto pc = connection();
    if (!pc) {
      return PeerConnectionState::kClosed;
    }
    return _surfacedConnectionState.Get(pc->peer_connection_state());
  }

  RTCPeerConnection::SignalingState RTCPeerConnection::GetSignalingState() {
    auto pc = connection();
    if (!pc) {
      return SignalingState::kClosed;
    }
    return _surfacedSignalingState.Get(pc->signaling_state());
  }

  RTCPeerConnection::IceConnectionState RTCPeerConnection::GetIceConnectionState() {
    auto pc = connection();
    if (!pc) {
      return IceConnectionState::kIceConnectionClosed;
    }
    return _surfacedIceConnectionState.Get(pc->standardized_ice_connection_state());
  }

  RTCPeerConnection::IceGatheringState RTCPeerConnection::GetIceGatheringState() {
    auto pc = connection();
    if (!pc) {
      return IceGatheringState::kIceGatheringComplete;
    }
    return _surfacedIceGatheringState.Get(pc->ice_gathering_state());
  }

  void RTCPeerConnection::OnSignalingChange(SignalingState newState) {
    _surfacedSignalingState.Changed(HasListeners(), _lastSignalingState);
    _lastSignalingState = newState;
    // the descriptions change along with the event
    Emit("signalingstatechange", newState, SnapshotDescriptions());
  }

  void RTCPeerConnection::OnIceConnectionChange(IceConnectionState /*unused*/) {
    // the legacy state, iceConnectionState is the standardized one
  }

  void RTCPeerConnection::OnStandardizedIceConnectionChange(IceConnectionState newState) {
    _surfacedIceConnectionState.Changed(HasListeners(), _lastIceConnectionState);
    _lastIceConnectionState = newState;
    Emit("iceconnectionstatechange", newState);
  }

  void RTCPeerConnection::OnConnectionChange(PeerConnectionState newState) {
    _surfacedConnectionState.Changed(HasListeners(), _lastConnectionState);
    _lastConnectionState = newState;
    Emit("connectionstatechange", newState);
  }

  void RTCPeerConnection::OnRenegotiationNeeded() {
    // the legacy event, negotiationneeded is fired by OnNegotiationNeededEvent
  }

  void RTCPeerConnection::OnNegotiationNeededEvent(uint32_t eventId) {
    Emit("negotiationneeded", eventId);
  }

  void RTCPeerConnection::OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> dataChannel) {
    // the channel holds its events until Python has delivered this one, if it's going to
    auto channel = Wrap(_channels, dataChannel);
    channel->OnAnnounced();
    if (!HasListeners()) {
      channel->Release();
    }
    Emit("datachannel", channel);
  }

  void RTCPeerConnection::OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> /*unused*/) {}

  void RTCPeerConnection::OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> /*unused*/) {}

  void
  RTCPeerConnection::OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> /*unused*/,
                                const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> & /*unused*/) {}

  void RTCPeerConnection::OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
    // a rejected media section (port 0) negotiates no track, but libwebrtc still reports it
    auto pc = connection();
    const auto *description = pc ? pc->remote_description() : nullptr;
    auto mid = transceiver->mid();
    if ((description != nullptr) && mid) {
      const auto *content = description->description()->GetContentByName(*mid);
      if ((content != nullptr) && content->rejected) {
        return;
      }
    }

    {
      const std::scoped_lock lock(_remoteStreamsMutex);
      _trackFired.insert(transceiver.get());
    }
    EmitTrack(transceiver);
  }

  void RTCPeerConnection::OnRemoveTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {
    // the remote track isn't negotiated anymore, which mutes it
    if (auto wrapper = RTCRtpReceiver::holder().Find(receiver.get())) {
      wrapper->GetTrack()->SetMuted(true);
    }
  }

  void RTCPeerConnection::EmitTrack(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver) {
    auto wrapper = Wrap(_transceivers, transceiver);
    auto receiver = Wrap(_receivers, transceiver->receiver());
    std::vector<std::shared_ptr<MediaStream>> streams;
    for (const auto &stream : transceiver->receiver()->streams()) {
      streams.push_back(MediaStream::holder().GetOrCreate(_factory, stream));
    }
    Emit("track", wrapper, receiver, streams);
  }

  namespace {

    std::vector<std::string>
    remoteStreamIds(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver) {
      std::vector<std::string> ids;
      for (const auto &stream : transceiver->receiver()->streams()) {
        ids.push_back(stream->id());
      }
      return ids;
    }

  } // namespace

  void RTCPeerConnection::SnapshotRemoteStreams(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
    std::map<const void *, std::vector<std::string>> before;
    for (const auto &transceiver : pc->GetTransceivers()) {
      before[transceiver.get()] = remoteStreamIds(transceiver);
    }
    const std::scoped_lock lock(_remoteStreamsMutex);
    _remoteStreamsBefore = std::move(before);
    _trackFired.clear();
  }

  void RTCPeerConnection::FireRemoteStreamChanges() {
    auto pc = connection();
    const auto *description = pc ? pc->remote_description() : nullptr;
    if (description == nullptr) {
      return;
    }
    std::map<const void *, std::vector<std::string>> before;
    std::set<const void *> fired;
    {
      const std::scoped_lock lock(_remoteStreamsMutex);
      std::swap(before, _remoteStreamsBefore);
      std::swap(fired, _trackFired);
    }
    for (const auto &transceiver : pc->GetTransceivers()) {
      auto mid = transceiver->mid();
      const auto *content = mid ? description->description()->GetContentByName(*mid) : nullptr;
      auto previous = before.find(transceiver.get());
      if ((content == nullptr) || content->rejected || fired.contains(transceiver.get()) || previous == before.end() ||
          !webrtc::RtpTransceiverDirectionHasSend(content->media_description()->direction())) {
        continue;
      }
      // the remote peer associates the track it sends with other streams: a track event tells about them
      if (remoteStreamIds(transceiver) != previous->second) {
        EmitTrack(transceiver);
      }
    }
  }

} // namespace python_webrtc
