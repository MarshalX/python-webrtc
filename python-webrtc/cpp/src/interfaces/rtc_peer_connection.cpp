//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"

#include <algorithm>
#include <limits>
#include <set>
#include <thread>

#include <absl/strings/match.h>
#include <media/base/media_constants.h>
#include <pc/rtp_media_utils.h>
#include <pc/session_description.h>

#include "peer_connection_factory.h"
#include "create_session_description_observer.h"
#include "set_session_description_observer.h"
#include "stats_collector_callback.h"
#include "../models/python_webrtc/rtc_ice_candidate.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  // what libwebrtc offers in its descriptions, and assumes without a max-message-size (RFC 8841)
  static constexpr double kLocalMaxMessageSize = 256 * 1024;
  static constexpr double kDefaultRemoteMaxMessageSize = 65536;

  // the snapshots Python didn't apply (like while it has no loop) aren't going to be
  static constexpr size_t kMaxPendingSnapshots = 32;

  class RTCPeerConnection::HeldOperationEvents {
  public:
    HeldOperationEvents(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                        std::vector<std::shared_ptr<RTCIceTransport>> iceTransports,
                        const std::shared_ptr<RTCPeerConnection> &connection) {
      if (connection) {
        connection->_heldGathering.Hold();
        _connection = connection;
      }
      for (auto &iceTransport: iceTransports) {
        if (!iceTransport->IsHeld()) {
          iceTransport->Hold();
          _iceTransports.push_back(std::move(iceTransport));
        }
      }
      for (const auto &transceiver: pc->GetTransceivers()) {
        auto track = MediaStreamTrack::holder().Find(transceiver->receiver()->track().get());
        if (track) {
          track->HoldEnded();
          _tracks.emplace_back(std::move(track));
        }
      }
    }

    // also when the operation fails before it starts
    ~HeldOperationEvents() { Release(); }

    void Release() {
      std::lock_guard<std::mutex> lock(_mutex);
      for (const auto &track: _tracks) {
        track->ReleaseEnded();
      }
      _tracks.clear();
      for (const auto &iceTransport: _iceTransports) {
        iceTransport->Release();
      }
      _iceTransports.clear();
      if (auto connection = _connection.lock()) {
        connection->_heldGathering.Release();
      }
      _connection.reset();
    }

  private:
    std::mutex _mutex;
    std::vector<std::shared_ptr<MediaStreamTrack>> _tracks;
    std::vector<std::shared_ptr<RTCIceTransport>> _iceTransports;
    // whose gathering is held
    std::weak_ptr<RTCPeerConnection> _connection;
  };

  RTCPeerConnection::RTCPeerConnection(const std::optional<ConfigurationInit> &init)
      : _factory(PeerConnectionFactory::GetOrCreateDefault()), _configuration(init.value_or(ConfigurationInit())) {
    auto configuration = webrtc::PeerConnectionInterface::RTCConfiguration();
    configuration.sdp_semantics = webrtc::SdpSemantics::kUnifiedPlan;
    configuration = _configuration.Apply(configuration);

    webrtc::PeerConnectionDependencies dependencies(this);

    auto result = _factory->factory()->CreatePeerConnectionOrError(
        configuration, std::move(dependencies));

    if (!result.ok()) {
      throw RTCException(result.error());
    }

    _jinglePeerConnection = result.MoveValue();
  }

  RTCPeerConnection::~RTCPeerConnection() {
    // destroying the peer connection blocks on the signaling thread, which may be waiting for the GIL
    BlockingDestructor release("RTCPeerConnection");

    // closing stops the connection from calling this observer
    Close();

    // released here, without the GIL, as it blocks on the signaling thread
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> closed;
    {
      std::lock_guard<std::mutex> lock(_connectionMutex);
      closed = std::move(_closedConnection);
    }
    closed = nullptr;
    DropListeners();
  }

  void RTCPeerConnection::Init(pybind11::module &m) {
    Listeners::BindClass<RTCPeerConnection>(m, "RTCPeerConnection")
        .def(pybind11::init(nogil_factory(+[](const std::optional<ConfigurationInit> &configuration) {
          return std::shared_ptr<RTCPeerConnection>(new RTCPeerConnection(configuration), DeleteOffLibwebrtcThread());
        })))
        .def("createOffer", &RTCPeerConnection::CreateOffer, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("iceRestart"),
             pybind11::arg("voiceActivityDetection"))
        .def("createAnswer", &RTCPeerConnection::CreateAnswer, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("voiceActivityDetection"))
        .def("setLocalDescription", &RTCPeerConnection::SetLocalDescription, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("description"))
        .def("setRemoteDescription", &RTCPeerConnection::SetRemoteDescription, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("description"))
        .def("addIceCandidate", &RTCPeerConnection::AddIceCandidate, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("candidate"),
             pybind11::arg("sdpMid"), pybind11::arg("sdpMLineIndex"), pybind11::arg("usernameFragment"))
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>>(
                 &RTCPeerConnection::AddTrack), nogil(), pybind11::arg("track"), pybind11::arg("stream"))
        .def("addTrack",
             pybind11::overload_cast<MediaStreamTrack &, const std::vector<MediaStream *> &>(
                 &RTCPeerConnection::AddTrack), nogil(), pybind11::arg("track"), pybind11::arg("streams"))
        .def("removeTrack", &RTCPeerConnection::RemoveTrack, nogil(), pybind11::arg("sender"))
        .def("addTransceiver",
             pybind11::overload_cast<webrtc::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), nogil(), pybind11::arg("kind"), pybind11::arg("init"))
        .def("addTransceiver",
             pybind11::overload_cast<MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &>(
                 &RTCPeerConnection::AddTransceiver), nogil(), pybind11::arg("track"), pybind11::arg("init"))
        .def("getTransceivers", &RTCPeerConnection::GetTransceivers, nogil())
        .def("getSenders", &RTCPeerConnection::GetSenders, nogil())
        .def("getReceivers", &RTCPeerConnection::GetReceivers, nogil())
        .def("createDataChannel", &RTCPeerConnection::CreateDataChannel, nogil(),
             pybind11::arg("label"), pybind11::arg("ordered"), pybind11::arg("maxPacketLifeTime"),
             pybind11::arg("maxRetransmits"), pybind11::arg("protocol"), pybind11::arg("negotiated"),
             pybind11::arg("id"), pybind11::arg("priority"))
        .def("getStats", &RTCPeerConnection::GetStats, nogil(), pybind11::arg("onSuccess"), pybind11::arg("onFailure"))
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
        .def("_surfaceSignalingState", &RTCPeerConnection::SurfaceSignalingState, nogil(),
             pybind11::arg("state"))
        .def("_surfaceIceConnectionState", &RTCPeerConnection::SurfaceIceConnectionState, nogil(),
             pybind11::arg("state"))
        .def("_surfaceIceGatheringState", &RTCPeerConnection::SurfaceIceGatheringState, nogil(),
             pybind11::arg("state"))
        .def("_surfaceConnectionState", &RTCPeerConnection::SurfaceConnectionState, nogil(),
             pybind11::arg("state"))
        .def("_refreshDescriptions", &RTCPeerConnection::RefreshDescriptions, nogil())
        .def_static("_connectionOf", &RTCPeerConnection::ConnectionOf, nogil(), pybind11::arg("sender"))
        .def("_applyDescriptions", &RTCPeerConnection::ApplyDescriptions, nogil(),
             pybind11::arg("snapshot") = std::nullopt);
  }

  void RTCPeerConnection::ReleaseElsewhere(std::shared_ptr<RTCPeerConnection> &&connection) {
    if (connection) {
      std::thread([connection = std::move(connection)]() mutable { connection = nullptr; }).detach();
    }
  }

  std::optional<std::shared_ptr<RTCPeerConnection>> RTCPeerConnection::ConnectionOf(RTCRtpSender &sender) {
    if (auto connection = sender.GetConnection()) {
      return connection;
    }
    return std::nullopt;
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::connection() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _jinglePeerConnection;
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::closedConnection() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _closedConnection;
  }

  bool RTCPeerConnection::IsClosed() {
    return !connection();
  }

  template<typename T, typename U>
  std::shared_ptr<T> RTCPeerConnection::Wrap(Wrappers<T, U> &wrappers, webrtc::scoped_refptr<U> object) {
    if (!onLibwebrtcThread) {
      // on the signaling thread, which wraps objects too: the lock isn't held while waiting for it
      gil_release_if_held release;
      return _factory->_signalingThread->BlockingCall([&]() { return Wrap(wrappers, std::move(object)); });
    }
    std::shared_ptr<T> wrapper;
    {
      std::lock_guard<std::mutex> lock(_wrappersMutex);
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

  template<typename T, typename U>
  std::vector<std::shared_ptr<T>> RTCPeerConnection::Sync(
      Wrappers<T, U> &wrappers, const std::vector<webrtc::scoped_refptr<U>> &objects) {
    if (!onLibwebrtcThread) {
      // see Wrap
      gil_release_if_held release;
      return _factory->_signalingThread->BlockingCall([&]() { return Sync(wrappers, objects); });
    }
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
    for (const auto &wrapper: result) {
      Adopt(wrapper);
    }
    // wrappers of the objects that are gone are released here, out of the lock
    return result;
  }

  template<typename T, typename U>
  std::vector<std::shared_ptr<T>> RTCPeerConnection::Unkept(const std::vector<webrtc::scoped_refptr<U>> &objects) {
    std::vector<std::shared_ptr<T>> result;
    for (const auto &object: objects) {
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
      std::lock_guard<std::mutex> lock(_wrappersMutex);
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

  static webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiverOf(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
      const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender) {
    for (const auto &transceiver: pc->GetTransceivers()) {
      if (transceiver->sender() == sender) {
        return transceiver;
      }
    }
    return nullptr;
  }

  static webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiverOf(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
      const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver) {
    for (const auto &transceiver: pc->GetTransceivers()) {
      if (transceiver->receiver() == receiver) {
        return transceiver;
      }
    }
    return nullptr;
  }

  // The media section a transceiver negotiated, in the current remote (for the sender) or local (for the receiver)
  // description; null until it's negotiated, and when it's rejected. On the signaling thread.
  static const webrtc::MediaContentDescription *negotiatedContent(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
      const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver, bool remote) {
    auto mid = transceiver ? transceiver->mid() : std::nullopt;
    auto description = remote ? pc->current_remote_description() : pc->current_local_description();
    auto content = mid && description ? description->description()->GetContentByName(*mid) : nullptr;
    return content && !content->rejected ? content->media_description() : nullptr;
  }

  static bool isSupported(const webrtc::Codec &codec, const webrtc::RtpCapabilities &capabilities,
                          webrtc::MediaType kind) {
    return std::any_of(capabilities.codecs.begin(), capabilities.codecs.end(), [&](const auto &capability) {
      return absl::EqualsIgnoreCase(capability.name, codec.name) &&
             capability.clock_rate == codec.clockrate &&
             (kind != webrtc::MediaType::AUDIO || static_cast<size_t>(capability.num_channels.value_or(1)) == codec.channels);
    });
  }

  // the codecs of a media section this side can use (the remote peer may list unknown ones)
  static std::vector<webrtc::RtpCodecParameters> supportedCodecs(
      const webrtc::MediaContentDescription &content, const webrtc::RtpCapabilities &capabilities) {
    std::set<int> kept;
    for (const auto &codec: content.codecs()) {
      if (codec.GetResiliencyType() != webrtc::Codec::ResiliencyType::kRtx &&
          isSupported(codec, capabilities, content.type())) {
        kept.insert(codec.id);
      }
    }
    std::vector<webrtc::RtpCodecParameters> codecs;
    for (const auto &codec: content.codecs()) {
      // a retransmission codec goes with the codec it retransmits
      int associated;
      bool rtx = codec.GetResiliencyType() == webrtc::Codec::ResiliencyType::kRtx;
      if (rtx ? codec.GetParam(webrtc::kCodecParamAssociatedPayloadType, &associated) && kept.count(associated)
              : kept.count(codec.id)) {
        codecs.push_back(codec.ToCodecParameters());
      }
    }
    return codecs;
  }

  webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> RTCPeerConnection::TransceiverOf(
      const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender) {
    auto pc = connection();
    return pc ? transceiverOf(pc, sender) : nullptr;
  }

  std::vector<webrtc::RtpCodecParameters> RTCPeerConnection::NegotiatedCodecs(
      const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return _factory->_signalingThread->BlockingCall([&]() {
      auto content = negotiatedContent(pc, transceiverOf(pc, sender), true);
      return content ? supportedCodecs(*content, _factory->factory()->GetRtpSenderCapabilities(content->type()))
                     : std::vector<webrtc::RtpCodecParameters>();
    });
  }

  std::vector<webrtc::RtpCodecParameters> RTCPeerConnection::NegotiatedCodecs(
      const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return _factory->_signalingThread->BlockingCall([&]() {
      auto content = negotiatedContent(pc, transceiverOf(pc, receiver), false);
      return content ? supportedCodecs(*content, _factory->factory()->GetRtpReceiverCapabilities(content->type()))
                     : std::vector<webrtc::RtpCodecParameters>();
    });
  }

  std::vector<webrtc::RtpExtension> RTCPeerConnection::NegotiatedHeaderExtensions(
      const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return _factory->_signalingThread->BlockingCall([&]() {
      auto content = negotiatedContent(pc, transceiverOf(pc, receiver), false);
      return content ? content->rtp_header_extensions() : std::vector<webrtc::RtpExtension>();
    });
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::StatsConnection(
      const std::function<void(RTCCallbackException)> &onFailure) {
    auto pc = connection();
    if (!pc) {
      pc = closedConnection();
    }
    if (!pc) {
      onFailure(RTCCallbackException(closedError("getStats")));
      return nullptr;
    }
    pc->ClearStatsCache();
    return pc;
  }

  void RTCPeerConnection::GetStats(std::function<void(std::string)> &onSuccess,
                                   std::function<void(RTCCallbackException)> &onFailure) {
    if (auto pc = StatsConnection(onFailure)) {
      pc->GetStats(webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess).get());
    }
  }

  void RTCPeerConnection::CollectStats(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender,
                                       std::function<void(std::string)> &onSuccess,
                                       std::function<void(RTCCallbackException)> &onFailure) {
    if (auto pc = StatsConnection(onFailure)) {
      pc->GetStats(sender, webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess));
    }
  }

  void RTCPeerConnection::CollectStats(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver,
                                       std::function<void(std::string)> &onSuccess,
                                       std::function<void(RTCCallbackException)> &onFailure) {
    auto pc = StatsConnection(onFailure);
    if (!pc) {
      return;
    }
    // a stopped transceiver receives no RTP streams anymore
    std::set<std::string> excluded;
    auto transceiver = transceiverOf(pc, receiver);
    if (transceiver && (transceiver->stopping() || transceiver->stopped())) {
      excluded.insert("inbound-rtp");
    }
    pc->GetStats(receiver, webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess, std::move(excluded)));
  }

  void RTCPeerConnection::CreateOffer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      bool iceRestart, bool voiceActivityDetection) {
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      onFailure(RTCCallbackException(closedError("createOffer")));
      return;
    }
    if (state != SignalingState::kStable && state != SignalingState::kHaveLocalOffer) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'createOffer' on 'RTCPeerConnection': Called in wrong state: " +
          std::string(webrtc::PeerConnectionInterface::AsString(state))));
      return;
    }

    auto observer = new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), onSuccess, onFailure);

    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    options.ice_restart = iceRestart;
    options.voice_activity_detection = voiceActivityDetection;

    pc->CreateOffer(observer, options);
  }

  void RTCPeerConnection::CreateAnswer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      bool voiceActivityDetection) {
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      onFailure(RTCCallbackException(closedError("createAnswer")));
      return;
    }

    auto observer = new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), onSuccess, onFailure);
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    options.voice_activity_detection = voiceActivityDetection;
    pc->CreateAnswer(observer, options);
  }

  void RTCPeerConnection::SaveCreatedDescription(const RTCSessionDescriptionInit &description) {
    std::lock_guard<std::mutex> lock(_createdMutex);
    (description.type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer) = description.sdp;
  }

  // A remote TCP candidate on a port Fetch blocks is ignored, as the WebRTC specification requires
  // (https://fetch.spec.whatwg.org/#bad-port)
  static bool isBlockedCandidate(const webrtc::Candidate &candidate) {
    static const std::set<int> badPorts = {
        0, 1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95, 101, 102, 103, 104,
        109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515, 526,
        530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659, 4045,
        4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080};
    return candidate.protocol() == "tcp" && badPorts.count(candidate.address().port()) > 0;
  }

  static void removeBlockedCandidates(webrtc::SessionDescriptionInterface &description) {
    std::vector<std::unique_ptr<webrtc::IceCandidate>> blocked;
    for (size_t i = 0; i < description.number_of_mediasections(); ++i) {
      auto candidates = description.candidates(i);
      for (size_t j = 0; candidates && j < candidates->count(); ++j) {
        auto candidate = candidates->at(j);
        if (isBlockedCandidate(candidate->candidate())) {
          blocked.push_back(webrtc::CreateIceCandidate(
              candidate->sdp_mid(), candidate->sdp_mline_index(), candidate->candidate()));
        }
      }
    }
    for (const auto &candidate: blocked) {
      description.RemoveCandidate(candidate.get());
    }
  }

  // the line of an SDP parse error, counting from 1
  static std::optional<int> lineNumber(const std::string &sdp, const std::string &line) {
    auto pos = line.empty() ? std::string::npos : sdp.find(line);
    if (pos == std::string::npos) {
      return std::nullopt;
    }
    return 1 + static_cast<int>(std::count(sdp.begin(), sdp.begin() + static_cast<std::ptrdiff_t>(pos), '\n'));
  }

  static std::unique_ptr<webrtc::SessionDescriptionInterface> parseDescription(
      const RTCSessionDescriptionInit &init, std::optional<RTCCallbackException> &error) {
    webrtc::SdpParseError parseError;
    auto description = webrtc::CreateSessionDescription(init.type, init.sdp, &parseError);
    if (!description) {
      webrtc::RTCError rtcError(webrtc::RTCErrorType::OPERATION_ERROR_WITH_DATA,
                                "Failed to parse the session description: " + parseError.description +
                                (parseError.line.empty() ? "" : " (" + parseError.line + ")"));
      rtcError.set_error_detail(webrtc::RTCErrorDetailType::SDP_SYNTAX_ERROR);
      error.emplace(std::move(rtcError), lineNumber(init.sdp, parseError.line));
    }
    return description;
  }

  static bool canSetLocal(webrtc::SdpType type, RTCPeerConnection::SignalingState state) {
    using SignalingState = RTCPeerConnection::SignalingState;
    if (type == webrtc::SdpType::kOffer) {
      return state == SignalingState::kStable || state == SignalingState::kHaveLocalOffer;
    }
    if (type == webrtc::SdpType::kRollback) {
      return state == SignalingState::kHaveLocalOffer || state == SignalingState::kHaveLocalPrAnswer;
    }
    return state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
  }

  std::function<void(webrtc::RTCError)> RTCPeerConnection::Completion(
      std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc, DescriptionKind kind) {
    bool remote = kind == DescriptionKind::kRemote;
    // a local description starts gathering, the candidates come after it
    auto held = std::make_shared<HeldOperationEvents>(pc, IceTransports(), remote ? nullptr : shared_from_this());
    if (remote) {
      SnapshotRemoteStreams(pc);
    }
    return [weak = weak_from_this(), onSuccess, onFailure, held, remote](webrtc::RTCError error) {
      auto self = weak.lock();
      if (!self || self->IsClosed()) {
        onFailure(RTCCallbackException(closedError(remote ? "setRemoteDescription" : "setLocalDescription")));
      } else if (error.ok()) {
        // the descriptions as the operation left them, before candidates gathered later
        self->_completionSnapshot = self->SnapshotDescriptions();
        auto created = self->WrapTransports();
        self->MarkIceRolesKnown();
        if (remote) {
          self->RecordRemoteDescriptionCandidates();
          // before the operation resolves, as the track events of a description are
          self->FireRemoteStreamChanges();
        }
        onSuccess();
        // their gathering events come after the operation
        for (const auto &iceTransport: created) {
          iceTransport->CreatedByDescription();
        }
      } else {
        onFailure(RTCCallbackException(std::move(error)));
      }
      held->Release();
      ReleaseElsewhere(std::move(self));
    };
  }

  void RTCPeerConnection::SetLocalDescription(
      std::function<void()> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      const std::optional<RTCSessionDescriptionInit> &init) {
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      onFailure(RTCCallbackException(closedError("setLocalDescription")));
      return;
    }
    if (init && !canSetLocal(init->type, state)) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The description type doesn't match "
          "the signaling state."));
      return;
    }

    if (!init || (init->sdp.empty() && init->type != webrtc::SdpType::kRollback)) {
      // without a type, an answer in the states that wait for one, an offer otherwise
      bool waitsForAnswer = state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
      auto type = init ? init->type : (waitsForAnswer ? webrtc::SdpType::kAnswer : webrtc::SdpType::kOffer);
      auto complete = Completion(onSuccess, onFailure, pc, DescriptionKind::kLocal);
      if (type == webrtc::SdpType::kOffer || (type == webrtc::SdpType::kAnswer && state == SignalingState::kHaveRemoteOffer)) {
        // libwebrtc creates the offer or the answer the signaling state calls for
        pc->SetLocalDescription(webrtc::make_ref_counted<SetLocalDescriptionObserver>(std::move(complete)));
      } else {
        SetImplicitAnswer(pc, type, std::move(complete), onFailure);
      }
      return;
    }

    if (init->type != webrtc::SdpType::kRollback) {
      std::lock_guard<std::mutex> lock(_createdMutex);
      auto &last = init->type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer;
      if (init->sdp != last) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
            "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The SDP does not match the previously "
            "generated SDP for this type"));
        return;
      }
    }

    std::optional<RTCCallbackException> error;
    auto description = parseDescription(*init, error);
    if (error) {
      onFailure(*error);
      return;
    }
    pc->SetLocalDescription(std::move(description), webrtc::make_ref_counted<SetLocalDescriptionObserver>(
        Completion(onSuccess, onFailure, pc, DescriptionKind::kLocal)));
  }

  void RTCPeerConnection::SetImplicitAnswer(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc, webrtc::SdpType type,
      std::function<void(webrtc::RTCError)> complete, const std::function<void(RTCCallbackException)> &onFailure) {
    auto observer = webrtc::make_ref_counted<SetLocalDescriptionObserver>(std::move(complete));
    auto apply = [pc, observer, type, onFailure](const std::string &sdp) {
      std::optional<RTCCallbackException> error;
      auto description = parseDescription(RTCSessionDescriptionInit(type, sdp), error);
      if (error) {
        onFailure(*error);
        return;
      }
      pc->SetLocalDescription(std::move(description), observer);
    };
    std::string lastAnswer;
    {
      std::lock_guard<std::mutex> lock(_createdMutex);
      lastAnswer = _lastAnswer;
    }
    if (!lastAnswer.empty()) {
      apply(lastAnswer);
      return;
    }
    std::function<void(RTCSessionDescription)> created = [apply](RTCSessionDescription answer) {
      apply(answer.init().sdp);
    };
    std::function<void(RTCCallbackException)> failed = onFailure;
    pc->CreateAnswer(new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), created, failed),
                     webrtc::PeerConnectionInterface::RTCOfferAnswerOptions());
  }

  void RTCPeerConnection::SetRemoteDescription(
      std::function<void()> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      const RTCSessionDescriptionInit &init) {
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      onFailure(RTCCallbackException(closedError("setRemoteDescription")));
      return;
    }

    // the state is checked before the SDP is parsed
    bool answer = init.type == webrtc::SdpType::kAnswer || init.type == webrtc::SdpType::kPrAnswer;
    bool rollback = init.type == webrtc::SdpType::kRollback;
    if ((answer && state != SignalingState::kHaveLocalOffer && state != SignalingState::kHaveRemotePrAnswer) ||
        (rollback && state != SignalingState::kHaveRemoteOffer && state != SignalingState::kHaveRemotePrAnswer)) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': Called in wrong state: " +
          std::string(webrtc::PeerConnectionInterface::AsString(state))));
      return;
    }

    auto complete = Completion(onSuccess, onFailure, pc, DescriptionKind::kRemote);
    auto apply = [init, complete, onFailure](webrtc::scoped_refptr<webrtc::PeerConnectionInterface> pc) {
      std::optional<RTCCallbackException> error;
      auto description = parseDescription(init, error);
      if (error) {
        onFailure(*error);
        return;
      }
      removeBlockedCandidates(*description);
      pc->SetRemoteDescription(std::move(description), webrtc::make_ref_counted<SetRemoteDescriptionObserver>(complete));
    };

    if (init.type == webrtc::SdpType::kOffer && state == SignalingState::kHaveLocalOffer) {
      // an offer in have-local-offer rolls the local one back first (perfect negotiation),
      // even if the offer turns out to be invalid
      auto rollbackObserver = webrtc::make_ref_counted<SetLocalDescriptionObserver>(
          [weak = weak_from_this(), apply, complete](webrtc::RTCError rollbackError) {
            auto self = weak.lock();
            auto pc = self ? self->connection() : nullptr;
            if (!rollbackError.ok()) {
              complete(std::move(rollbackError));
            } else if (!pc) {
              complete(closedError("setRemoteDescription"));
            } else {
              apply(pc);
            }
            ReleaseElsewhere(std::move(self));
          });
      pc->SetLocalDescription(webrtc::CreateSessionDescription(webrtc::SdpType::kRollback, ""), rollbackObserver);
      return;
    }

    apply(pc);
  }

  // End-of-candidates candidates of a local description, one per transport (the first media section of each)
  static std::vector<IceCandidateInit> endOfCandidates(const webrtc::SessionDescriptionInterface *description) {
    std::vector<IceCandidateInit> result;
    if (!description) {
      return result;
    }
    auto session = description->description();
    auto bundle = session->GetGroupByName(webrtc::GROUP_TYPE_BUNDLE);
    bool bundleDone = false;
    int index = 0;
    for (const auto &content: session->contents()) {
      auto mid = content.mid();
      bool bundled = bundle && bundle->HasContentName(mid);
      if (!content.rejected && !(bundled && bundleDone)) {
        auto transport = session->GetTransportInfoByName(mid);
        std::optional<std::string> ufrag;
        if (transport && !transport->description.ice_ufrag.empty()) {
          ufrag = transport->description.ice_ufrag;
        }
        result.emplace_back(mid, index, ufrag);
        bundleDone = bundleDone || bundled;
      }
      ++index;
    }
    return result;
  }

  // Adds a=end-of-candidates to the media sections of a description (of these mids, or all of them)
  static std::string addEndOfCandidates(const std::string &sdp, const std::set<std::string> *mids = nullptr) {
    std::string result;
    bool inMedia = false, rejected = false, ended = false;
    std::string mid;
    auto endSection = [&]() {
      if (inMedia && !rejected && !ended && (!mids || mids->count(mid))) {
        result += "a=end-of-candidates\r\n";
      }
    };
    size_t pos = 0;
    while (pos < sdp.size()) {
      auto end = sdp.find("\r\n", pos);
      auto line = sdp.substr(pos, end == std::string::npos ? std::string::npos : end - pos);
      if (line.rfind("m=", 0) == 0) {
        endSection();
        inMedia = true;
        ended = false;
        // a rejected media section has port 0
        auto space = line.find(' ');
        rejected = space != std::string::npos && line.compare(space + 1, 2, "0 ") == 0;
        mid.clear();
      } else if (line == "a=end-of-candidates") {
        ended = true;
      } else if (line.rfind("a=mid:", 0) == 0) {
        mid = line.substr(6);
      }
      result += line + "\r\n";
      if (end == std::string::npos) {
        break;
      }
      pos = end + 2;
    }
    endSection();
    return result;
  }

  static std::vector<const webrtc::SessionDescriptionInterface *> liveDescriptions(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
    return {pc->current_local_description(), pc->current_remote_description(),
            pc->pending_local_description(), pc->pending_remote_description()};
  }

  RTCPeerConnection::DescriptionView RTCPeerConnection::ReadDescription(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc, DescriptionKind kind) {
    DescriptionView view;
    switch (kind) {
      case DescriptionKind::kLocal: view.description = pc->local_description(); break;
      case DescriptionKind::kRemote: view.description = pc->remote_description(); break;
      case DescriptionKind::kCurrentLocal: view.description = pc->current_local_description(); break;
      case DescriptionKind::kCurrentRemote: view.description = pc->current_remote_description(); break;
      case DescriptionKind::kPendingLocal: view.description = pc->pending_local_description(); break;
      case DescriptionKind::kPendingRemote: view.description = pc->pending_remote_description(); break;
    }
    if (!view.description) {
      return view;
    }
    auto &init = view.init.emplace(
        RTCSessionDescriptionInit::Wrap(const_cast<webrtc::SessionDescriptionInterface *>(view.description)));
    bool local = kind == DescriptionKind::kLocal || kind == DescriptionKind::kCurrentLocal ||
                 kind == DescriptionKind::kPendingLocal;
    if (local && pc->ice_gathering_state() == IceGatheringState::kIceGatheringComplete) {
      init.sdp = addEndOfCandidates(init.sdp);
    } else if (!local && view.description == pc->remote_description()) {
      // the end of remote candidates, from addIceCandidate
      std::lock_guard<std::mutex> lock(_remoteEndOfCandidatesMutex);
      if (_remoteEndOfCandidatesDescription == view.description && !_remoteEndOfCandidates.empty()) {
        init.sdp = addEndOfCandidates(init.sdp, &_remoteEndOfCandidates);
      }
    }
    return view;
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetDescription(DescriptionKind kind) {
    auto pc = connection();
    if (!pc) {
      return nullptr;
    }

    DescriptionView view;
    std::vector<const webrtc::SessionDescriptionInterface *> live;
    bool shown = false;
    {
      // the descriptions as the last event that changed them left them, until the next one
      std::lock_guard<std::mutex> lock(_descriptionsMutex);
      if (HasListeners() && _shown && _shownGeneration == _descriptionsGeneration) {
        view = _shown->kinds[static_cast<size_t>(kind)];
        live = _shown->live;
        shown = true;
      }
    }
    if (!shown) {
      // the description is owned by the peer connection and must be read on the signaling thread
      _factory->_signalingThread->BlockingCall([&]() {
        view = ReadDescription(pc, kind);
        live = liveDescriptions(pc);
      });
    }

    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    // while events are delivered, a description only changes with them; without events it's always current
    bool refresh = shown || !HasListeners() || _descriptionsCachedGeneration != _descriptionsGeneration;
    _descriptionsCachedGeneration = _descriptionsGeneration;
    return FindOrCreateDescription(view, live, refresh);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::FindOrCreateDescription(
      const DescriptionView &view, const std::vector<const webrtc::SessionDescriptionInterface *> &live,
      bool refresh) {
    // descriptions that aren't set anymore are forgotten, so a new one at the same address is a new object
    std::vector<std::pair<const webrtc::SessionDescriptionInterface *, std::shared_ptr<RTCSessionDescription>>> kept;
    std::shared_ptr<RTCSessionDescription> result;
    for (auto &entry: _descriptions) {
      if (std::find(live.begin(), live.end(), entry.first) == live.end()) {
        continue;
      }
      auto &init = entry.second->init();
      if (entry.first == view.description && init.type == view.init->type && (!refresh || init.sdp == view.init->sdp)) {
        result = entry.second;
      }
      kept.push_back(std::move(entry));
    }
    if (view.description && !result) {
      result = std::make_shared<RTCSessionDescription>(*view.init);
      kept.emplace_back(view.description, result);
    }
    std::swap(_descriptions, kept);
    return result;
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetLocalDescription() {
    return GetDescription(DescriptionKind::kLocal);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetRemoteDescription() {
    return GetDescription(DescriptionKind::kRemote);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetCurrentLocalDescription() {
    return GetDescription(DescriptionKind::kCurrentLocal);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetCurrentRemoteDescription() {
    return GetDescription(DescriptionKind::kCurrentRemote);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetPendingLocalDescription() {
    return GetDescription(DescriptionKind::kPendingLocal);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetPendingRemoteDescription() {
    return GetDescription(DescriptionKind::kPendingRemote);
  }

  uint64_t RTCPeerConnection::SnapshotDescriptions() {
    auto pc = connection();
    if (!pc || !HasListeners()) {
      return 0;
    }
    DescriptionsSnapshot snapshot;
    for (size_t kind = 0; kind < kDescriptionKinds; ++kind) {
      snapshot.kinds[kind] = ReadDescription(pc, static_cast<DescriptionKind>(kind));
    }
    snapshot.live = liveDescriptions(pc);
    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    auto id = ++_lastSnapshot;
    _snapshots.emplace(id, std::move(snapshot));
    while (_snapshots.size() > kMaxPendingSnapshots) {
      _snapshots.erase(_snapshots.begin());
    }
    return id;
  }

  void RTCPeerConnection::ApplyDescriptions(std::optional<uint64_t> snapshot) {
    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    auto it = _snapshots.find(snapshot.value_or(_completionSnapshot));
    if (it == _snapshots.end()) {
      return;
    }
    // shown until the next event that changes them
    _shown = std::move(it->second);
    _shownGeneration = _descriptionsGeneration;
    _snapshots.erase(_snapshots.begin(), std::next(it));
  }

  void RTCPeerConnection::RefreshDescriptions() {
    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    ++_descriptionsGeneration;
  }

  std::optional<bool> RTCPeerConnection::GetCanTrickleIceCandidates() {
    auto pc = connection();
    return pc ? pc->can_trickle_ice_candidates() : std::nullopt;
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, const std::vector<MediaStream *> &mediaStreams) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("addTrack"));
    }

    std::vector<std::string> streamIds;
    streamIds.reserve(mediaStreams.size());
    for (auto const &stream: mediaStreams) {
      streamIds.emplace_back(stream->stream()->id());
    }

    auto result = pc->AddTrack(mediaStreamTrack.track(), streamIds);
    if (!result.ok()) {
      throw RTCException(result.error());
    }

    QueueNegotiationNeeded();
    return Wrap(_senders, result.value());
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, std::optional<std::reference_wrapper<MediaStream>> mediaStream) {
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

    auto senders = pc->GetSenders();
    if (std::find(senders.begin(), senders.end(), sender.sender()) == senders.end()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_PARAMETER, "The sender was not created by this RTCPeerConnection");
    }

    auto error = pc->RemoveTrackOrError(sender.sender());
    if (!error.ok()) {
      throw RTCException(error);
    }
    QueueNegotiationNeeded();
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      webrtc::MediaType kind, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("addTransceiver"));
    }
    return AddedTransceiver(init ? pc->AddTransceiver(kind, init->get()) : pc->AddTransceiver(kind));
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      MediaStreamTrack &track, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init) {
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
    return closed ? Unkept<RTCRtpTransceiver>(closed->GetTransceivers()) : std::vector<std::shared_ptr<RTCRtpTransceiver>>();
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

  std::shared_ptr<RTCDataChannel> RTCPeerConnection::CreateDataChannel(
      const std::string &label, bool ordered, std::optional<int> maxPacketLifeTime, std::optional<int> maxRetransmits,
      const std::string &protocol, bool negotiated, std::optional<int> id, webrtc::Priority priority) {
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
                         ? error.type() : webrtc::RTCErrorType::UNSUPPORTED_OPERATION, error.message());
    }
    QueueNegotiationNeeded();
    return Wrap(_channels, result.MoveValue());
  }

  std::optional<std::shared_ptr<RTCSctpTransport>> RTCPeerConnection::GetSctp() {
    if (!onLibwebrtcThread) {
      // see Wrap
      gil_release_if_held release;
      return _factory->_signalingThread->BlockingCall([this]() { return GetSctp(); });
    }
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
    return _factory->_signalingThread->BlockingCall([&pc]() -> std::optional<double> {
      auto sctpSize = [](const webrtc::SessionDescriptionInterface *description) -> std::optional<int> {
        if (!description) {
          return {};
        }
        for (const auto &content: description->description()->contents()) {
          auto *sctp = content.media_description() ? content.media_description()->as_sctp() : nullptr;
          if (sctp && !content.rejected) {
            return sctp->max_message_size();
          }
        }
        return {};
      };
      double canSendSize = sctpSize(pc->current_local_description()).value_or(kLocalMaxMessageSize);
      // updated once the description is negotiated, when an answer is set
      double remoteSize = sctpSize(pc->current_remote_description()).value_or(kDefaultRemoteMaxMessageSize);
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
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _configuration;
  }

  void RTCPeerConnection::SetConfiguration(const ConfigurationInit &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(closedError("setConfiguration"));
    }

    {
      std::lock_guard<std::mutex> lock(_connectionMutex);
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

    std::lock_guard<std::mutex> lock(_connectionMutex);
    auto certificates = _configuration.certificates;
    _configuration = init;
    if (!_configuration.certificates) {
      _configuration.certificates = certificates;
    }
  }

  void RTCPeerConnection::RestartIce() {
    auto pc = connection();
    // before the first local description, there are no credentials to replace: the first offer has new ones
    if (pc && pc->local_description()) {
      pc->RestartIce();
      QueueNegotiationNeeded();
    }
  }

  void RTCPeerConnection::QueueNegotiationNeeded() {
    // libwebrtc posts the negotiationneeded event of a change to the signaling thread: once the thread ran it,
    // the event is queued during the call
    _factory->_signalingThread->BlockingCall([]() {});
  }

  bool RTCPeerConnection::ShouldFireNegotiationNeededEvent(uint32_t eventId) {
    auto pc = connection();
    return pc && pc->ShouldFireNegotiationNeededEvent(eventId);
  }

  void RTCPeerConnection::Close() {
    // closing changes states, but a closed connection fires no events, nor do its channels and transports
    Mute();
    {
      std::lock_guard<std::mutex> lock(_wrappersMutex);
      for (auto &channel: _channels) {
        channel.second->OnPeerConnectionClosed();
      }
    }
    MuteTransports();

    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> pc;
    {
      std::lock_guard<std::mutex> lock(_connectionMutex);
      pc = std::move(_jinglePeerConnection);
      if (pc) {
        _closedConnection = pc;
      }
    }

    if (pc) {
      pc->Close();
      for (const auto &transceiver: pc->GetTransceivers()) {
        Wrap(_transceivers, transceiver)->GetReceiver()->GetTrack()->OnPeerConnectionClosed();
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

  void RTCPeerConnection::OnIceConnectionChange(IceConnectionState) {
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

  template<typename... Args>
  void RTCPeerConnection::EmitGathering(const char *name, Args... args) {
    _heldGathering.Emit([this, name, args...]() { Emit(name, args...); });
  }

  void RTCPeerConnection::OnIceGatheringChange(IceGatheringState newState) {
    _surfacedIceGatheringState.Changed(HasListeners(), _lastIceGatheringState);
    _lastIceGatheringState = newState;
    if (newState != IceGatheringState::kIceGatheringComplete) {
      EmitGathering("icegatheringstatechange", newState);
      return;
    }

    // every transport ends its candidates with an empty one
    auto pc = connection();
    for (auto &candidate: endOfCandidates(pc ? pc->local_description() : nullptr)) {
      EmitGathering("icecandidate", candidate);
    }
    // then, in a single task, the ICE transports and the connection complete, and the candidates end
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    for (const auto &iceTransport: IceTransports()) {
      if (iceTransport->IsHeld()) {
        // Python doesn't have it yet: its completion waits along with its other events
        iceTransport->EmitGatheringComplete();
      } else {
        iceTransports.push_back(iceTransport);
      }
    }
    EmitGathering("_gatheringcomplete", iceTransports, newState);
  }

  void RTCPeerConnection::OnIceCandidate(const webrtc::IceCandidateInterface *candidate) {
    // the candidate is only valid during the call
    if (candidate) {
      IceCandidateInit init(*candidate);
      if (auto iceTransport = IceTransportByMid(candidate->sdp_mid())) {
        iceTransport->AddLocalCandidate(init);
      }
      EmitGathering("icecandidate", init);
    }
  }

  void RTCPeerConnection::OnIceCandidateError(const std::string &address, int port, const std::string &url,
                                              int errorCode, const std::string &errorText) {
    Emit("icecandidateerror", address, port, url, errorCode, errorText);
  }

  // the DTLS transports of the media sections and of the data channels, some of them shared (bundled)
  static std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> dtlsTransports(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> transports;
    for (const auto &transceiver: pc->GetTransceivers()) {
      transports.push_back(transceiver->sender()->dtls_transport());
      transports.push_back(transceiver->receiver()->dtls_transport());
    }
    if (auto sctp = pc->GetSctpTransport()) {
      transports.push_back(sctp->dtls_transport());
    }
    transports.erase(std::remove(transports.begin(), transports.end(), nullptr), transports.end());
    return transports;
  }

  std::vector<std::shared_ptr<RTCIceTransport>> RTCPeerConnection::IceTransports() {
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    auto pc = connection();
    if (!pc) {
      return iceTransports;
    }
    for (const auto &transport: dtlsTransports(pc)) {
      auto dtls = RTCDtlsTransport::holder().Find(transport.get());
      auto ice = dtls ? dtls->GetIceTransport() : nullptr;
      if (ice && std::find(iceTransports.begin(), iceTransports.end(), ice) == iceTransports.end()) {
        iceTransports.push_back(ice);
      }
    }
    return iceTransports;
  }

  std::shared_ptr<RTCIceTransport> RTCPeerConnection::IceTransportByMid(const std::string &mid) {
    auto pc = connection();
    auto dtls = pc && !mid.empty() ? pc->LookupDtlsTransportByMid(mid) : nullptr;
    auto wrapper = dtls ? RTCDtlsTransport::holder().Find(dtls.get()) : nullptr;
    return wrapper ? wrapper->GetIceTransport() : nullptr;
  }

  std::vector<std::shared_ptr<RTCIceTransport>> RTCPeerConnection::WrapTransports() {
    std::vector<std::shared_ptr<RTCIceTransport>> created;
    auto pc = connection();
    if (!pc) {
      return created;
    }
    std::vector<std::shared_ptr<RTCDtlsTransport>> wrappers;
    for (const auto &transport: dtlsTransports(pc)) {
      bool existed = RTCDtlsTransport::holder().Find(transport.get()) != nullptr;
      auto wrapper = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);
      if (!existed) {
        // Python doesn't have the transports yet, their events wait for it
        wrapper->Hold();
        wrapper->GetIceTransport()->Hold();
        Adopt(wrapper);
      }
      if (std::find(wrappers.begin(), wrappers.end(), wrapper) == wrappers.end()) {
        if (!existed) {
          created.push_back(wrapper->GetIceTransport());
        }
        wrappers.push_back(std::move(wrapper));
      }
    }
    {
      std::lock_guard<std::mutex> lock(_wrappersMutex);
      std::swap(_dtlsTransports, wrappers);
    }
    // wrappers of transports that are gone are released here, out of the lock
    return created;
  }

  void RTCPeerConnection::MuteTransports() {
    auto pc = connection();
    if (!pc) {
      return;
    }

    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> transports;
    webrtc::scoped_refptr<webrtc::SctpTransportInterface> sctpTransport;
    _factory->_signalingThread->BlockingCall([&]() {
      transports = dtlsTransports(pc);
      sctpTransport = pc->GetSctpTransport();
    });

    if (auto sctp = sctpTransport ? RTCSctpTransport::holder().Find(sctpTransport.get()) : nullptr) {
      sctp->OnPeerConnectionClosed();
    }
    for (const auto &transport: transports) {
      if (auto dtls = RTCDtlsTransport::holder().Find(transport.get())) {
        dtls->OnPeerConnectionClosed();
        dtls->GetIceTransport()->OnPeerConnectionClosed();
      }
    }
  }

  void RTCPeerConnection::MarkIceRolesKnown() {
    auto pc = connection();
    if (!pc) {
      return;
    }
    auto state = pc->signaling_state();
    if (state == SignalingState::kStable || state == SignalingState::kHaveLocalPrAnswer ||
        state == SignalingState::kHaveRemotePrAnswer) {
      for (const auto &iceTransport: IceTransports()) {
        iceTransport->SetRoleKnown();
      }
    }
  }

  void RTCPeerConnection::RecordRemoteCandidate(const IceCandidateInit &candidate) {
    auto mid = candidate.sdpMid;
    auto pc = connection();
    if (mid.empty() && pc) {
      // signaled by the index of its media section
      _factory->_signalingThread->BlockingCall([&]() {
        auto description = pc->remote_description();
        auto &contents = description ? description->description()->contents()
                                     : std::vector<webrtc::ContentInfo>();
        if (candidate.sdpMLineIndex >= 0 && static_cast<size_t>(candidate.sdpMLineIndex) < contents.size()) {
          mid = contents[candidate.sdpMLineIndex].mid();
        }
      });
    }
    if (auto iceTransport = IceTransportByMid(mid)) {
      iceTransport->AddRemoteCandidate(candidate);
    }
  }

  void RTCPeerConnection::RecordRemoteDescriptionCandidates() {
    auto pc = connection();
    auto description = pc ? pc->remote_description() : nullptr;
    if (!description) {
      return;
    }
    const auto &contents = description->description()->contents();
    for (size_t index = 0; index < contents.size(); ++index) {
      auto iceTransport = IceTransportByMid(contents[index].mid());
      auto candidates = description->candidates(index);
      if (!iceTransport || !candidates) {
        continue;
      }
      for (const auto &candidate: candidates->candidates()) {
        iceTransport->AddRemoteCandidate(IceCandidateInit(*candidate));
      }
    }
  }

  std::optional<std::pair<std::string, std::string>> RTCPeerConnection::IceParameters(
      const webrtc::IceTransportInterface *iceTransport, bool local) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return _factory->_signalingThread->BlockingCall([&]() -> std::optional<std::pair<std::string, std::string>> {
      auto description = local ? pc->local_description() : pc->remote_description();
      if (!description) {
        return std::nullopt;
      }
      for (const auto &content: description->description()->contents()) {
        auto dtls = pc->LookupDtlsTransportByMid(content.mid());
        auto info = description->description()->GetTransportInfoByName(content.mid());
        if (dtls && dtls->ice_transport().get() == iceTransport && info) {
          return std::make_pair(info->description.ice_ufrag, info->description.ice_pwd);
        }
      }
      return std::nullopt;
    });
  }

  void RTCPeerConnection::OnIceSelectedCandidatePairChanged(const webrtc::CandidatePairChangeEvent &) {
    // the event doesn't tell which transport changed, the ICE transports that Python has check themselves
    for (const auto &ice: IceTransports()) {
      ice->CheckSelectedCandidatePair();
    }
  }

  void RTCPeerConnection::AddIceCandidate(
      std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
      const std::string &candidate, const std::optional<std::string> &sdpMid, std::optional<int> sdpMLineIndex,
      const std::optional<std::string> &usernameFragment) {
    auto pc = connection();
    if (!pc) {
      onFailure(RTCCallbackException(closedError("addIceCandidate")));
      return;
    }

    // the media sections the candidate is for (all of them for a null mid and index), and whether its ufrag is known
    std::optional<RTCCallbackException> error;
    std::set<std::string> mids;
    const webrtc::SessionDescriptionInterface *remote = nullptr;
    _factory->_signalingThread->BlockingCall([&]() {
      remote = pc->remote_description();
      if (!remote) {
        error.emplace(webrtc::RTCErrorType::INVALID_STATE, "The remote description was null");
        return;
      }
      auto session = remote->description();
      auto &contents = session->contents();
      for (size_t i = 0; i < contents.size(); ++i) {
        bool matches = sdpMid ? contents[i].mid() == *sdpMid
                              : sdpMLineIndex ? static_cast<int>(i) == *sdpMLineIndex : true;
        if (matches && !contents[i].rejected) {
          mids.insert(contents[i].mid());
        }
      }
      if (mids.empty() && (sdpMid || sdpMLineIndex)) {
        error.emplace(webrtc::RTCErrorType::UNSUPPORTED_OPERATION, "The media section of the candidate was not found");
        return;
      }
      if (usernameFragment) {
        bool known = false;
        for (const auto &mid: mids) {
          auto transport = session->GetTransportInfoByName(mid);
          known = known || (transport && transport->description.ice_ufrag == *usernameFragment);
        }
        if (!known) {
          error.emplace(webrtc::RTCErrorType::UNSUPPORTED_OPERATION,
                        "The usernameFragment doesn't match the remote description");
        }
      }
    });
    if (error) {
      onFailure(*error);
      return;
    }

    if (candidate.empty()) {
      // the end of candidates, which libwebrtc doesn't take: the remote description shows it
      {
        std::lock_guard<std::mutex> lock(_remoteEndOfCandidatesMutex);
        if (_remoteEndOfCandidatesDescription != remote) {
          _remoteEndOfCandidates.clear();
          _remoteEndOfCandidatesDescription = remote;
        }
        _remoteEndOfCandidates.insert(mids.begin(), mids.end());
      }
      RefreshDescriptions();
      onSuccess();
      return;
    }

    webrtc::SdpParseError parseError;
    auto iceCandidate = webrtc::IceCandidate::Create(
        sdpMid.value_or(""), sdpMLineIndex.value_or(0), candidate, &parseError);
    if (!iceCandidate) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::UNSUPPORTED_OPERATION,
          "Failed to parse the ICE candidate: " + parseError.description));
      return;
    }

    if (isBlockedCandidate(iceCandidate->candidate())) {
      onSuccess();
      return;
    }

    auto added = std::make_shared<IceCandidateInit>(*iceCandidate);
    auto complete = [weak = weak_from_this(), onSuccess, onFailure, added](webrtc::RTCError error) {
      if (error.ok()) {
        // the remote description has the candidate now
        if (auto self = weak.lock()) {
          self->RecordRemoteCandidate(*added);
          self->RefreshDescriptions();
          ReleaseElsewhere(std::move(self));
        }
        onSuccess();
      } else {
        onFailure(RTCCallbackException(std::move(error)));
      }
    };
    pc->AddIceCandidate(std::move(iceCandidate), complete);
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

  void RTCPeerConnection::OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface>) {}

  void RTCPeerConnection::OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface>) {}

  void RTCPeerConnection::OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface>,
                                     const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &) {}

  void RTCPeerConnection::OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) {
    // a rejected media section (port 0) negotiates no track, but libwebrtc still reports it
    auto pc = connection();
    auto description = pc ? pc->remote_description() : nullptr;
    auto mid = transceiver->mid();
    if (description && mid) {
      auto content = description->description()->GetContentByName(*mid);
      if (content && content->rejected) {
        return;
      }
    }

    {
      std::lock_guard<std::mutex> lock(_remoteStreamsMutex);
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
    for (const auto &stream: transceiver->receiver()->streams()) {
      streams.push_back(MediaStream::holder().GetOrCreate(_factory, stream));
    }
    Emit("track", wrapper, receiver, streams);
  }

  static std::vector<std::string> remoteStreamIds(
      const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver) {
    std::vector<std::string> ids;
    for (const auto &stream: transceiver->receiver()->streams()) {
      ids.push_back(stream->id());
    }
    return ids;
  }

  void RTCPeerConnection::SnapshotRemoteStreams(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
    std::map<const void *, std::vector<std::string>> before;
    for (const auto &transceiver: pc->GetTransceivers()) {
      before[transceiver.get()] = remoteStreamIds(transceiver);
    }
    std::lock_guard<std::mutex> lock(_remoteStreamsMutex);
    _remoteStreamsBefore = std::move(before);
    _trackFired.clear();
  }

  void RTCPeerConnection::FireRemoteStreamChanges() {
    auto pc = connection();
    auto description = pc ? pc->remote_description() : nullptr;
    if (!description) {
      return;
    }
    std::map<const void *, std::vector<std::string>> before;
    std::set<const void *> fired;
    {
      std::lock_guard<std::mutex> lock(_remoteStreamsMutex);
      std::swap(before, _remoteStreamsBefore);
      std::swap(fired, _trackFired);
    }
    for (const auto &transceiver: pc->GetTransceivers()) {
      auto mid = transceiver->mid();
      auto content = mid ? description->description()->GetContentByName(*mid) : nullptr;
      auto previous = before.find(transceiver.get());
      if (!content || content->rejected || fired.count(transceiver.get()) || previous == before.end() ||
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
