//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"
#include "../utils/gil.h"

#include <algorithm>
#include <limits>
#include <set>
#include <thread>

#include "peer_connection_factory.h"
#include "create_session_description_observer.h"
#include "set_session_description_observer.h"
#include "stats_collector_callback.h"
#include "media_stream_track.h"
#include "../models/python_webrtc/rtc_ice_candidate.h"

#include <absl/strings/match.h>
#include <media/base/media_constants.h>
#include <pc/rtp_media_utils.h>
#include <pc/session_description.h>

namespace python_webrtc {

  using SignalingState = webrtc::PeerConnectionInterface::SignalingState;

  // A connection referenced in a callback of libwebrtc may be released there, while it can't be destroyed on the
  // signaling thread in the middle of its own callback: the reference is released on a thread of its own
  static void ReleaseElsewhere(std::shared_ptr<RTCPeerConnection> &&connection) {
    if (connection) {
      std::thread([connection = std::move(connection)]() mutable { connection = nullptr; }).detach();
    }
  }


  RTCPeerConnection::RTCPeerConnection(const std::optional<ConfigurationInit> &init)
      : _factory(PeerConnectionFactory::GetOrCreateDefault()), _configuration(init.value_or(ConfigurationInit())) {
    auto configuration = webrtc::PeerConnectionInterface::RTCConfiguration();
    configuration.sdp_semantics = webrtc::SdpSemantics::kUnifiedPlan;
    configuration = _configuration.Apply(configuration);

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
    DropListeners();

    // released here, without the GIL, as it blocks on the signaling thread
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> closed;
    {
      std::lock_guard<std::mutex> lock(_connectionMutex);
      closed = std::move(_closedConnection);
    }
    closed = nullptr;
  }

  template<typename T, typename U>
  std::shared_ptr<T> RTCPeerConnection::Wrap(Wrappers<T, U> &wrappers, webrtc::scoped_refptr<U> object) {
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

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpSender> &sender) {
    auto weak = weak_from_this();
    auto key = static_cast<const void *>(sender->sender().get());
    sender->SetNegotiatedCodecs([weak, key]() {
      auto self = weak.lock();
      return self ? self->NegotiatedCodecs(key, true) : std::vector<webrtc::RtpCodecParameters>();
    });
    auto rawSender = sender->sender();
    sender->SetStatsGetter([weak, rawSender](std::function<void(std::string)> onSuccess,
                                             std::function<void(RTCCallbackException)> onFailure) {
      auto self = weak.lock();
      auto pc = self ? self->statsConnection() : nullptr;
      if (!pc) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection is gone"));
        return;
      }
      // libwebrtc reuses a report for 50 ms, the stats are the current ones
      pc->ClearStatsCache();
      pc->GetStats(rawSender, webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess));
    });
    sender->SetTransceiver([weak, rawSender]() -> webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> {
      auto self = weak.lock();
      auto pc = self ? self->connection() : nullptr;
      if (!pc) {
        return nullptr;
      }
      for (const auto &transceiver: pc->GetTransceivers()) {
        if (transceiver->sender() == rawSender) {
          return transceiver;
        }
      }
      return nullptr;
    });
    sender->SetConnectionClosed([weak]() {
      auto self = weak.lock();
      return !self || self->IsClosed();
    });
    sender->SetConnection([weak]() { return weak.lock(); });
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpReceiver> &receiver) {
    auto weak = weak_from_this();
    auto key = static_cast<const void *>(receiver->receiver().get());
    receiver->SetNegotiatedCodecs([weak, key]() {
      auto self = weak.lock();
      return self ? self->NegotiatedCodecs(key, false) : std::vector<webrtc::RtpCodecParameters>();
    });
    receiver->SetNegotiatedHeaderExtensions([weak, key]() {
      auto self = weak.lock();
      return self ? self->NegotiatedHeaderExtensions(key) : std::vector<webrtc::RtpExtension>();
    });
    auto rawReceiver = receiver->receiver();
    receiver->SetStatsGetter([weak, rawReceiver](std::function<void(std::string)> onSuccess,
                                                 std::function<void(RTCCallbackException)> onFailure) {
      auto self = weak.lock();
      auto pc = self ? self->statsConnection() : nullptr;
      if (!pc) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection is gone"));
        return;
      }
      // a stopped transceiver receives no RTP streams anymore
      std::set<std::string> excluded;
      for (const auto &transceiver: pc->GetTransceivers()) {
        if (transceiver->receiver() == rawReceiver && (transceiver->stopping() || transceiver->stopped())) {
          excluded.insert("inbound-rtp");
        }
      }
      pc->ClearStatsCache();
      pc->GetStats(rawReceiver, webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess, std::move(excluded)));
    });
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCDataChannel> &channel) {
    auto weak = weak_from_this();
    channel->SetMaxMessageSizeGetter([weak]() -> std::optional<double> {
      auto self = weak.lock();
      auto sctp = self ? self->GetSctp() : std::nullopt;
      return sctp ? (*sctp)->GetMaxMessageSize() : std::nullopt;
    });
  }

  // As the specification updates the data max message size: the max-message-size of the negotiated remote
  // description (65536 without it), limited by what the local side can send, where 0 means no limit
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
      // what libwebrtc offers in its descriptions
      double canSendSize = sctpSize(pc->current_local_description()).value_or(256 * 1024);
      // updated once the description is negotiated, when an answer is set
      double remoteSize = sctpSize(pc->current_remote_description()).value_or(65536);
      if (remoteSize == 0 && canSendSize == 0) {
        return std::numeric_limits<double>::infinity();
      }
      if (remoteSize == 0 || canSendSize == 0) {
        return std::max(remoteSize, canSendSize);
      }
      return std::min(remoteSize, canSendSize);
    });
  }

  void RTCPeerConnection::Adopt(const std::shared_ptr<RTCRtpTransceiver> &transceiver) {
    auto weak = weak_from_this();
    transceiver->SetConnectionClosed([weak]() {
      auto self = weak.lock();
      return !self || self->IsClosed();
    });
    Adopt(transceiver->GetSender());
    Adopt(transceiver->GetReceiver());
  }

  std::vector<webrtc::RtpCodecParameters> RTCPeerConnection::NegotiatedCodecs(const void *senderOrReceiver, bool send) {
    auto pc = connection();
    std::vector<webrtc::RtpCodecParameters> codecs;
    if (!pc) {
      return codecs;
    }
    _factory->_signalingThread->BlockingCall([&]() {
      for (const auto &transceiver: pc->GetTransceivers()) {
        auto object = send ? static_cast<const void *>(transceiver->sender().get())
                           : static_cast<const void *>(transceiver->receiver().get());
        auto mid = transceiver->mid();
        if (object != senderOrReceiver || !mid) {
          continue;
        }
        // only once negotiated
        auto description = send ? pc->current_remote_description() : pc->current_local_description();
        auto content = description ? description->description()->GetContentByName(*mid) : nullptr;
        if (content && !content->rejected) {
          // only the codecs this side can use, of the ones the remote peer listed (it may list unknown ones)
          auto kind = content->media_description()->type();
          auto capabilities = send ? _factory->factory()->GetRtpSenderCapabilities(kind)
                                   : _factory->factory()->GetRtpReceiverCapabilities(kind);
          auto supported = [&](const webrtc::Codec &codec) {
            return std::any_of(capabilities.codecs.begin(), capabilities.codecs.end(), [&](const auto &capability) {
              return absl::EqualsIgnoreCase(capability.name, codec.name) &&
                     capability.clock_rate == codec.clockrate &&
                     (kind != webrtc::MediaType::AUDIO || capability.num_channels.value_or(1) == codec.channels);
            });
          };
          std::set<int> kept;
          for (const auto &codec: content->media_description()->codecs()) {
            if (supported(codec) && codec.GetResiliencyType() != webrtc::Codec::ResiliencyType::kRtx) {
              kept.insert(codec.id);
            }
          }
          for (const auto &codec: content->media_description()->codecs()) {
            // a retransmission codec goes with the codec it retransmits
            int associated;
            bool rtx = codec.GetResiliencyType() == webrtc::Codec::ResiliencyType::kRtx;
            if (rtx ? codec.GetParam(webrtc::kCodecParamAssociatedPayloadType, &associated) && kept.count(associated)
                    : kept.count(codec.id)) {
              codecs.push_back(codec.ToCodecParameters());
            }
          }
        }
      }
    });
    return codecs;
  }

  std::vector<webrtc::RtpExtension> RTCPeerConnection::NegotiatedHeaderExtensions(const void *receiver) {
    auto pc = connection();
    std::vector<webrtc::RtpExtension> extensions;
    if (!pc) {
      return extensions;
    }
    _factory->_signalingThread->BlockingCall([&]() {
      for (const auto &transceiver: pc->GetTransceivers()) {
        auto mid = transceiver->mid();
        if (static_cast<const void *>(transceiver->receiver().get()) != receiver || !mid) {
          continue;
        }
        auto description = pc->current_local_description();
        auto content = description ? description->description()->GetContentByName(*mid) : nullptr;
        if (content && !content->rejected) {
          extensions = content->media_description()->rtp_header_extensions();
        }
      }
    });
    return extensions;
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

  void RTCPeerConnection::Init(pybind11::module &m) {
    pybind11::class_<RTCPeerConnection, std::shared_ptr<RTCPeerConnection>> cls(
        m, "RTCPeerConnection", Listeners::TypeSetup<RTCPeerConnection>());
    Listeners::Bind(cls);
    cls
        .def(pybind11::init<const std::optional<ConfigurationInit> &>(), nogil())
        .def("getConfiguration", &RTCPeerConnection::GetConfiguration, nogil())
        .def("setConfiguration", &RTCPeerConnection::SetConfiguration, nogil())
        .def("addIceCandidate", &RTCPeerConnection::AddIceCandidate, nogil())
        .def("getStats", &RTCPeerConnection::GetStats, nogil())
        .def("createDataChannel", &RTCPeerConnection::CreateDataChannel, nogil())
        .def("_shouldFireNegotiationNeededEvent", &RTCPeerConnection::ShouldFireNegotiationNeededEvent, nogil())
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
        .def_property_readonly("remoteDescription", nogil_fn(&RTCPeerConnection::GetRemoteDescription))
        .def_property_readonly("currentLocalDescription", nogil_fn(&RTCPeerConnection::GetCurrentLocalDescription))
        .def_property_readonly("currentRemoteDescription", nogil_fn(&RTCPeerConnection::GetCurrentRemoteDescription))
        .def_property_readonly("pendingLocalDescription", nogil_fn(&RTCPeerConnection::GetPendingLocalDescription))
        .def_property_readonly("pendingRemoteDescription", nogil_fn(&RTCPeerConnection::GetPendingRemoteDescription))
        .def_property_readonly("canTrickleIceCandidates", nogil_fn([](RTCPeerConnection &self) -> std::optional<bool> {
          auto pc = self.connection();
          return pc ? pc->can_trickle_ice_candidates() : std::nullopt;
        }))
        .def("_surface", &RTCPeerConnection::SurfaceState, nogil())
        .def("_refreshDescriptions", &RTCPeerConnection::RefreshDescriptions, nogil())
        .def("_applyDescriptions", &RTCPeerConnection::ApplySnapshot, nogil(), pybind11::arg("snapshot") = std::nullopt);
  }

  void RTCPeerConnection::SaveLastSdp(const RTCSessionDescriptionInit &lastSdp) {
    std::lock_guard<std::mutex> lock(_lastSdpMutex);
    _lastSdp = lastSdp;
    (lastSdp.type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer) = lastSdp.sdp;
  }

  void RTCPeerConnection::CreateOffer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      bool iceRestart, std::optional<bool> offerToReceiveAudio, std::optional<bool> offerToReceiveVideo,
      bool voiceActivityDetection) {
    auto pc = connection();
    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'createOffer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."
      ));
      return;
    }

    auto state = pc->signaling_state();
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
    // the legacy options add receiving transceivers (true) or stop receiving on the existing ones (false)
    if (offerToReceiveAudio) {
      options.offer_to_receive_audio = *offerToReceiveAudio ? 1 : 0;
    }
    if (offerToReceiveVideo) {
      options.offer_to_receive_video = *offerToReceiveVideo ? 1 : 0;
    }

    pc->CreateOffer(observer, options);
  }

  void RTCPeerConnection::CreateAnswer(
      std::function<void(RTCSessionDescription)> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      bool voiceActivityDetection) {
    auto pc = connection();
    if (!pc ||
        pc->signaling_state() == webrtc::PeerConnectionInterface::SignalingState::kClosed) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'createAnswer' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    auto observer = new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), onSuccess, onFailure);
    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    options.voice_activity_detection = voiceActivityDetection;
    pc->CreateAnswer(observer, options);
  }

  // A remote TCP candidate on a port Fetch blocks is ignored, as the WebRTC specification requires
  // (https://fetch.spec.whatwg.org/#bad-port)
  static bool IsBlockedCandidate(const webrtc::Candidate &candidate) {
    static const std::set<int> badPorts = {
        0, 1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95, 101, 102, 103, 104,
        109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515, 526,
        530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659, 4045,
        4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080};
    return candidate.protocol() == "tcp" && badPorts.count(candidate.address().port()) > 0;
  }

  static void RemoveBlockedCandidates(webrtc::SessionDescriptionInterface &description) {
    std::vector<std::unique_ptr<webrtc::IceCandidate>> blocked;
    for (size_t i = 0; i < description.number_of_mediasections(); ++i) {
      auto candidates = description.candidates(i);
      for (size_t j = 0; candidates && j < candidates->count(); ++j) {
        auto candidate = candidates->at(j);
        if (IsBlockedCandidate(candidate->candidate())) {
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
  static std::optional<int> LineNumber(const std::string &sdp, const std::string &line) {
    auto pos = line.empty() ? std::string::npos : sdp.find(line);
    if (pos == std::string::npos) {
      return std::nullopt;
    }
    return 1 + static_cast<int>(std::count(sdp.begin(), sdp.begin() + static_cast<long>(pos), '\n'));
  }

  static std::unique_ptr<webrtc::SessionDescriptionInterface> ParseDescription(
      const RTCSessionDescriptionInit &init, std::optional<RTCCallbackException> &error) {
    webrtc::SdpParseError parseError;
    auto description = webrtc::CreateSessionDescription(init.type, init.sdp, &parseError);
    if (!description) {
      webrtc::RTCError rtcError(webrtc::RTCErrorType::OPERATION_ERROR_WITH_DATA,
                                "Failed to parse the session description: " + parseError.description +
                                (parseError.line.empty() ? "" : " (" + parseError.line + ")"));
      rtcError.set_error_detail(webrtc::RTCErrorDetailType::SDP_SYNTAX_ERROR);
      error.emplace(std::move(rtcError), LineNumber(init.sdp, parseError.line));
    }
    return description;
  }

  static bool CanSetLocal(webrtc::SdpType type, SignalingState state) {
    if (type == webrtc::SdpType::kOffer) {
      return state == SignalingState::kStable || state == SignalingState::kHaveLocalOffer;
    }
    if (type == webrtc::SdpType::kRollback) {
      return state == SignalingState::kHaveLocalOffer || state == SignalingState::kHaveLocalPrAnswer;
    }
    return state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
  }

  // An operation that completes after close() fails, rather than never settling as in a browser, which in Python
  // would leave the caller waiting forever
  //
  // The ended events of the receiver tracks are held until the operation completes, so that they come after it,
  // as a browser queues them
  class HeldTracks {
  public:
    HeldTracks(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
               std::vector<std::shared_ptr<RTCIceTransport>> iceTransports,
               const std::shared_ptr<RTCPeerConnection> &gathering) {
      // the candidates a local description starts gathering come after it, as a browser queues them
      if (gathering) {
        gathering->HoldGathering();
        _gathering = gathering;
      }
      // ICE transport state changes the description causes (like checking) come after it too
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
    ~HeldTracks() { Release(); }

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
      if (auto gathering = _gathering.lock()) {
        gathering->ReleaseGathering();
      }
      _gathering.reset();
    }

  private:
    std::mutex _mutex;
    std::vector<std::shared_ptr<MediaStreamTrack>> _tracks;
    std::vector<std::shared_ptr<RTCIceTransport>> _iceTransports;
    std::weak_ptr<RTCPeerConnection> _gathering;
  };

  static std::function<void(webrtc::RTCError)> Completion(
      std::weak_ptr<RTCPeerConnection> connection,
      std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &native, bool remote = false) {
    auto owner = connection.lock();
    auto held = std::make_shared<HeldTracks>(
        native, owner ? owner->IceTransports() : std::vector<std::shared_ptr<RTCIceTransport>>(),
        remote ? nullptr : owner);
    if (remote) {
      if (auto pc = connection.lock()) {
        pc->SnapshotRemoteStreams(native);
      }
    }
    return [connection, onSuccess, onFailure, held, remote](webrtc::RTCError error) {
      auto pc = connection.lock();
      if (!pc || pc->IsClosed()) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection was closed"));
      } else if (error.ok()) {
        // the descriptions as the operation left them, before candidates gathered later
        pc->_completionSnapshot = pc->SnapshotDescriptions();
        auto created = pc->WrapTransports();
        pc->MarkIceRolesKnown();
        if (remote) {
          pc->RecordRemoteDescriptionCandidates();
          // before the operation resolves, as the track events of a description are
          pc->FireRemoteStreamChanges();
        }
        onSuccess();
        // after the description is set, as a browser queues it
        for (const auto &iceTransport: created) {
          iceTransport->CreatedByDescription();
        }
      } else {
        onFailure(wrapRTCErrorForCallback(error));
      }
      held->Release();
      ReleaseElsewhere(std::move(pc));
    };
  }

  void RTCPeerConnection::SetLocalDescription(
      std::function<void()> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      const std::optional<RTCSessionDescriptionInit> &init) {
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    // created right before the operation starts, as it holds the events of the receiver tracks
    auto observer = [&]() {
      return webrtc::make_ref_counted<SetLocalDescriptionObserver>(Completion(weak_from_this(), onSuccess, onFailure, pc));
    };
    auto state = pc->signaling_state();
    if (init && !CanSetLocal(init->type, state)) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The description type doesn't match "
          "the signaling state."));
      return;
    }

    if (!init || (init->sdp.empty() && init->type != webrtc::SdpType::kRollback)) {
      // without a type, an answer in the states that wait for one, an offer otherwise
      bool waitsForAnswer = state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
      auto type = init ? init->type : (waitsForAnswer ? webrtc::SdpType::kAnswer : webrtc::SdpType::kOffer);
      if (type == webrtc::SdpType::kOffer || (type == webrtc::SdpType::kAnswer && state == SignalingState::kHaveRemoteOffer)) {
        // implicit: libwebrtc creates the offer or the answer the signaling state calls for
        pc->SetLocalDescription(observer());
        return;
      }

      // a provisional answer, or the final one after it: [[LastCreatedAnswer]], or a new answer
      // (libwebrtc only makes final answers, and offers in have-local-pranswer)
      auto complete = observer();
      auto apply = [pc, complete, type, onFailure](const std::string &sdp) mutable {
        std::optional<RTCCallbackException> error;
        auto description = ParseDescription(RTCSessionDescriptionInit(type, sdp), error);
        if (error) {
          onFailure(*error);
          return;
        }
        pc->SetLocalDescription(std::move(description), complete);
      };
      std::string lastAnswer;
      {
        std::lock_guard<std::mutex> lock(_lastSdpMutex);
        lastAnswer = _lastAnswer;
      }
      if (!lastAnswer.empty()) {
        apply(lastAnswer);
        return;
      }
      std::function<void(RTCSessionDescription)> created = [apply](RTCSessionDescription answer) mutable {
        apply(answer.init().sdp);
      };
      std::function<void(RTCCallbackException)> failed = onFailure;
      pc->CreateAnswer(new webrtc::RefCountedObject<CreateSessionDescriptionObserver>(weak_from_this(), created, failed),
                       webrtc::PeerConnectionInterface::RTCOfferAnswerOptions());
      return;
    }

    if (init->type != webrtc::SdpType::kRollback) {
      std::lock_guard<std::mutex> lock(_lastSdpMutex);
      auto &last = init->type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer;
      if (init->sdp != last) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
            "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The SDP does not match the previously "
            "generated SDP for this type"));
        return;
      }
    }

    std::optional<RTCCallbackException> error;
    auto description = ParseDescription(*init, error);
    if (error) {
      onFailure(*error);
      return;
    }
    pc->SetLocalDescription(std::move(description), observer());
  }

  void RTCPeerConnection::SetRemoteDescription(
      std::function<void()> &onSuccess,
      std::function<void(RTCCallbackException)> &onFailure,
      const RTCSessionDescriptionInit &init) {
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
      return;
    }

    // the state is checked before the SDP is parsed
    auto state = pc->signaling_state();
    bool answer = init.type == webrtc::SdpType::kAnswer || init.type == webrtc::SdpType::kPrAnswer;
    bool rollback = init.type == webrtc::SdpType::kRollback;
    if ((answer && state != SignalingState::kHaveLocalOffer && state != SignalingState::kHaveRemotePrAnswer) ||
        (rollback && state != SignalingState::kHaveRemoteOffer && state != SignalingState::kHaveRemotePrAnswer)) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': Called in wrong state: " +
          std::string(webrtc::PeerConnectionInterface::AsString(state))));
      return;
    }

    auto complete = Completion(weak_from_this(), onSuccess, onFailure, pc, true);
    // parses and sets the description
    auto apply = [init, complete, onFailure](webrtc::scoped_refptr<webrtc::PeerConnectionInterface> pc) mutable {
      std::optional<RTCCallbackException> error;
      auto description = ParseDescription(init, error);
      if (error) {
        onFailure(*error);
        return;
      }
      RemoveBlockedCandidates(*description);
      pc->SetRemoteDescription(std::move(description), webrtc::make_ref_counted<SetRemoteDescriptionObserver>(complete));
    };

    if (init.type == webrtc::SdpType::kOffer && state == SignalingState::kHaveLocalOffer) {
      // an offer in have-local-offer rolls the local one back first (perfect negotiation),
      // even if the offer turns out to be invalid
      auto weak = weak_from_this();
      auto rollback = webrtc::make_ref_counted<SetLocalDescriptionObserver>(
          [weak, apply, complete](webrtc::RTCError rollbackError) mutable {
            auto self = weak.lock();
            auto pc = self ? self->connection() : nullptr;
            if (!rollbackError.ok()) {
              complete(std::move(rollbackError));
            } else if (!pc) {
              complete(webrtc::RTCError(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection was closed"));
            } else {
              apply(pc);
            }
            ReleaseElsewhere(std::move(self));
          });
      pc->SetLocalDescription(webrtc::CreateSessionDescription(webrtc::SdpType::kRollback, ""), rollback);
      return;
    }

    apply(pc);
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, const std::vector<MediaStream *> &mediaStreams) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Cannot add track; RTCPeerConnection is closed");
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
    QueueNegotiationNeeded();
    return Wrap(_senders, rtpSender);
  }

  std::shared_ptr<RTCRtpSender> RTCPeerConnection::AddTrack(
      MediaStreamTrack &mediaStreamTrack, std::optional<std::reference_wrapper<MediaStream>> mediaStream) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Cannot add track; RTCPeerConnection is closed");
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
    QueueNegotiationNeeded();
    return Wrap(_senders, rtpSender);
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      webrtc::MediaType kind, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Cannot add transceiver; RTCPeerConnection is closed");
    } else if (pc->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  pc->AddTransceiver(kind, init->get()) :
                  pc->AddTransceiver(kind);
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    QueueNegotiationNeeded();
    return Wrap(_transceivers, result.value());
  }

  std::shared_ptr<RTCRtpTransceiver> RTCPeerConnection::AddTransceiver(
      MediaStreamTrack &track, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init
  ) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Cannot add transceiver; RTCPeerConnection is closed");
    } else if (pc->GetConfiguration().sdp_semantics != webrtc::SdpSemantics::kUnifiedPlan) {
      throw PythonWebRTCException("AddTransceiver is only available with Unified Plan SdpSemanticsAbort");
    }

    auto result = init ?
                  pc->AddTransceiver(track.track(), init->get()) :
                  pc->AddTransceiver(track.track());
    if (!result.ok()) {
      throw wrapRTCError(result.error());
    }

    QueueNegotiationNeeded();
    return Wrap(_transceivers, result.value());
  }

  std::vector<std::shared_ptr<RTCRtpTransceiver>> RTCPeerConnection::GetTransceivers() {
    auto pc = connection();
    if (pc && pc->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan) {
      return Sync(_transceivers, pc->GetTransceivers());
    }
    auto closed = statsConnection();
    return closed ? Unkept<RTCRtpTransceiver>(closed->GetTransceivers()) : std::vector<std::shared_ptr<RTCRtpTransceiver>>();
  }

  std::vector<std::shared_ptr<RTCRtpSender>> RTCPeerConnection::GetSenders() {
    auto pc = connection();
    if (pc) {
      return Sync(_senders, pc->GetSenders());
    }
    // the transceivers of a closed connection are stopped, which leaves no senders and receivers
    return {};
  }

  std::vector<std::shared_ptr<RTCRtpReceiver>> RTCPeerConnection::GetReceivers() {
    auto pc = connection();
    if (pc) {
      return Sync(_receivers, pc->GetReceivers());
    }
    // the transceivers of a closed connection are stopped, which leaves no senders and receivers
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
      auto weak = weak_from_this();
      _sctp->SetMaxMessageSizeGetter([weak]() -> std::optional<double> {
        auto self = weak.lock();
        return self ? self->MaxMessageSize() : std::nullopt;
      });
    }
    return _sctp;
  }

  ConfigurationInit RTCPeerConnection::GetConfiguration() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _configuration;
  }

  void RTCPeerConnection::SetConfiguration(const ConfigurationInit &init) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection's signalingState is 'closed'.");
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
      throw wrapRTCError(error);
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
    // the event is queued, as a browser queues it during the call
    _factory->_signalingThread->BlockingCall([]() {});
  }

  void RTCPeerConnection::RemoveTrack(RTCRtpSender &sender) {
    auto pc = connection();
    if (!pc) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "Cannot remove track; RTCPeerConnection is closed");
    }

    auto senders = pc->GetSenders();
    if (std::find(senders.begin(), senders.end(), sender.sender()) == senders.end()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_PARAMETER, "The sender was not created by this RTCPeerConnection");
    }

    auto error = pc->RemoveTrackOrError(sender.sender());
    if (!error.ok()) {
      throw wrapRTCError(error);
    }
    QueueNegotiationNeeded();
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

      if (pc->GetConfiguration().sdp_semantics == webrtc::SdpSemantics::kUnifiedPlan) {
        for (const auto &transceiver: pc->GetTransceivers()) {
          Wrap(_transceivers, transceiver)->GetReceiver()->GetTrack()->OnPeerConnectionClosed();
        }
      }
    }

    // wrappers still referenced from Python keep their (closed) state
    ReleaseWrappers();
  }

  void RTCPeerConnection::OnRemoveTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) {
    // the remote track isn't negotiated anymore, which mutes it
    if (auto wrapper = RTCRtpReceiver::holder().Find(receiver.get())) {
      wrapper->GetTrack()->SetMuted(true);
    }
  }

  void RTCPeerConnection::OnIceSelectedCandidatePairChanged(const webrtc::CandidatePairChangeEvent &event) {
    // the event doesn't tell which transport changed, the ICE transports that Python has check themselves
    for (const auto &ice: IceTransports()) {
      ice->CheckSelectedCandidatePair();
    }
  }

  void RTCPeerConnection::MuteTransports() {
    auto pc = connection();
    if (!pc) {
      return;
    }

    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> dtlsTransports;
    webrtc::scoped_refptr<webrtc::SctpTransportInterface> sctpTransport;
    _factory->_signalingThread->BlockingCall([&]() {
      for (const auto &transceiver: pc->GetTransceivers()) {
        dtlsTransports.push_back(transceiver->sender()->dtls_transport());
        dtlsTransports.push_back(transceiver->receiver()->dtls_transport());
      }
      sctpTransport = pc->GetSctpTransport();
    });

    if (sctpTransport) {
      if (auto sctp = RTCSctpTransport::holder().Find(sctpTransport.get())) {
        sctp->OnPeerConnectionClosed();
      }
      dtlsTransports.push_back(sctpTransport->dtls_transport());
    }
    for (const auto &transport: dtlsTransports) {
      if (!transport) {
        continue;
      }
      if (auto dtls = RTCDtlsTransport::holder().Find(transport.get())) {
        dtls->OnPeerConnectionClosed();
        dtls->GetIceTransport()->OnPeerConnectionClosed();
      }
    }
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::statsConnection() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _jinglePeerConnection ? _jinglePeerConnection : _closedConnection;
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface> RTCPeerConnection::connection() {
    std::lock_guard<std::mutex> lock(_connectionMutex);
    return _jinglePeerConnection;
  }

  // End-of-candidates candidates of a local description, one per transport (the first media section of each)
  static std::vector<IceCandidateInit> EndOfCandidates(const webrtc::SessionDescriptionInterface *description) {
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
  static std::string AddEndOfCandidates(const std::string &sdp, const std::set<std::string> *mids = nullptr) {
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

  void RTCPeerConnection::ReadDescription(
      const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc, DescriptionKind kind,
      const webrtc::SessionDescriptionInterface *&description, std::optional<RTCSessionDescriptionInit> &init,
      std::vector<const webrtc::SessionDescriptionInterface *> &current) {
    switch (kind) {
      case DescriptionKind::kLocal: description = pc->local_description(); break;
      case DescriptionKind::kRemote: description = pc->remote_description(); break;
      case DescriptionKind::kCurrentLocal: description = pc->current_local_description(); break;
      case DescriptionKind::kCurrentRemote: description = pc->current_remote_description(); break;
      case DescriptionKind::kPendingLocal: description = pc->pending_local_description(); break;
      case DescriptionKind::kPendingRemote: description = pc->pending_remote_description(); break;
    }
    if (description) {
      init = RTCSessionDescriptionInit::Wrap(const_cast<webrtc::SessionDescriptionInterface *>(description));
      bool local = kind == DescriptionKind::kLocal || kind == DescriptionKind::kCurrentLocal ||
                   kind == DescriptionKind::kPendingLocal;
      if (local && pc->ice_gathering_state() == webrtc::PeerConnectionInterface::kIceGatheringComplete) {
        init->sdp = AddEndOfCandidates(init->sdp);
      } else if (!local && description == pc->remote_description()) {
        // the end of remote candidates, from addIceCandidate
        std::lock_guard<std::mutex> lock(_remoteEndOfCandidatesMutex);
        if (_remoteEndOfCandidatesDescription == description && !_remoteEndOfCandidates.empty()) {
          init->sdp = AddEndOfCandidates(init->sdp, &_remoteEndOfCandidates);
        }
      }
    }
    current = {pc->current_local_description(), pc->current_remote_description(),
               pc->pending_local_description(), pc->pending_remote_description()};
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::GetDescription(DescriptionKind kind) {
    auto pc = connection();
    if (!pc) {
      return nullptr;
    }

    const webrtc::SessionDescriptionInterface *description = nullptr;
    std::optional<RTCSessionDescriptionInit> init;
    std::vector<const webrtc::SessionDescriptionInterface *> current;
    bool shown = false;
    {
      // the descriptions as the last event that changed them left them, until the next one
      std::lock_guard<std::mutex> lock(_descriptionsMutex);
      if (HasListeners() && _shown && _shownGeneration == _descriptionsGeneration) {
        std::tie(description, init) = _shown->kinds[static_cast<size_t>(kind)];
        current = _shown->current;
        shown = true;
      }
    }
    if (!shown) {
      // the description is owned by the peer connection and must be read on the signaling thread
      _factory->_signalingThread->BlockingCall([&]() { ReadDescription(pc, kind, description, init, current); });
    }

    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    // while events are delivered, a description only changes with them; without events it's always current
    bool refresh = shown || !HasListeners() || _descriptionsCachedGeneration != _descriptionsGeneration;
    _descriptionsCachedGeneration = _descriptionsGeneration;
    // descriptions that aren't set anymore are forgotten, so a new one at the same address is a new object
    std::vector<std::pair<const webrtc::SessionDescriptionInterface *, std::shared_ptr<RTCSessionDescription>>> kept;
    std::shared_ptr<RTCSessionDescription> result;
    for (auto &entry: _descriptions) {
      if (std::find(current.begin(), current.end(), entry.first) != current.end()) {
        if (entry.first == description && entry.second->init().type == init->type &&
            (!refresh || entry.second->init().sdp == init->sdp)) {
          result = entry.second;
        }
        kept.push_back(std::move(entry));
      }
    }
    if (description && !result) {
      result = std::make_shared<RTCSessionDescription>(*init);
      kept.emplace_back(description, result);
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
    for (size_t kind = 0; kind < snapshot.kinds.size(); ++kind) {
      auto &[description, init] = snapshot.kinds[kind];
      ReadDescription(pc, static_cast<DescriptionKind>(kind), description, init, snapshot.current);
    }
    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    auto id = ++_lastSnapshot;
    _snapshots.emplace(id, std::move(snapshot));
    // the ones Python didn't apply (like while it has no loop) aren't going to be
    while (_snapshots.size() > 32) {
      _snapshots.erase(_snapshots.begin());
    }
    return id;
  }

  void RTCPeerConnection::ApplySnapshot(std::optional<uint64_t> id) {
    std::lock_guard<std::mutex> lock(_descriptionsMutex);
    auto it = _snapshots.find(id.value_or(_completionSnapshot));
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

  void RTCPeerConnection::SurfaceState(const std::string &event, int state) {
    using PC = webrtc::PeerConnectionInterface;
    if (event == "signalingstatechange") _surfacedSignalingState.Surface(static_cast<PC::SignalingState>(state));
    else if (event == "iceconnectionstatechange") _surfacedIceConnectionState.Surface(static_cast<PC::IceConnectionState>(state));
    else if (event == "icegatheringstatechange") _surfacedIceGatheringState.Surface(static_cast<PC::IceGatheringState>(state));
    else if (event == "connectionstatechange") _surfacedConnectionState.Surface(static_cast<PC::PeerConnectionState>(state));
  }

  webrtc::PeerConnectionInterface::PeerConnectionState RTCPeerConnection::GetConnectionState() {
    auto pc = connection();
    if (!pc) {
      return webrtc::PeerConnectionInterface::PeerConnectionState::kClosed;
    }
    return _surfacedConnectionState.Get(pc->peer_connection_state());
  }

  webrtc::PeerConnectionInterface::SignalingState RTCPeerConnection::GetSignalingState() {
    auto pc = connection();
    if (!pc) {
      return webrtc::PeerConnectionInterface::SignalingState::kClosed;
    }
    return _surfacedSignalingState.Get(pc->signaling_state());
  }

  webrtc::PeerConnectionInterface::IceConnectionState RTCPeerConnection::GetIceConnectionState() {
    auto pc = connection();
    if (!pc) {
      return webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionClosed;
    }
    return _surfacedIceConnectionState.Get(pc->standardized_ice_connection_state());
  }

  webrtc::PeerConnectionInterface::IceGatheringState RTCPeerConnection::GetIceGatheringState() {
    auto pc = connection();
    if (!pc) {
      return webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringComplete;
    }
    return _surfacedIceGatheringState.Get(pc->ice_gathering_state());
  }

  void RTCPeerConnection::OnSignalingChange(webrtc::PeerConnectionInterface::SignalingState new_state) {
    _surfacedSignalingState.Changed(HasListeners(), _lastSignalingState);
    _lastSignalingState = new_state;
    // the descriptions change along with the event
    Emit("signalingstatechange", new_state, SnapshotDescriptions());
  }

  void RTCPeerConnection::OnIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) {
    // the legacy state, iceConnectionState is the standardized one
  }

  void RTCPeerConnection::OnStandardizedIceConnectionChange(
      webrtc::PeerConnectionInterface::IceConnectionState new_state) {
    _surfacedIceConnectionState.Changed(HasListeners(), _lastIceConnectionState);
    _lastIceConnectionState = new_state;
    Emit("iceconnectionstatechange", new_state);
  }

  void RTCPeerConnection::OnConnectionChange(webrtc::PeerConnectionInterface::PeerConnectionState new_state) {
    _surfacedConnectionState.Changed(HasListeners(), _lastConnectionState);
    _lastConnectionState = new_state;
    Emit("connectionstatechange", new_state);
  }

  void RTCPeerConnection::OnIceGatheringChange(webrtc::PeerConnectionInterface::IceGatheringState new_state) {
    _surfacedIceGatheringState.Changed(HasListeners(), _lastIceGatheringState);
    _lastIceGatheringState = new_state;
    if (new_state != webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringComplete) {
      EmitGathering("icegatheringstatechange", new_state);
      return;
    }

    // every transport ends its candidates with an empty one
    auto pc = connection();
    for (auto &candidate: EndOfCandidates(pc ? pc->local_description() : nullptr)) {
      EmitGathering("icecandidate", candidate);
    }
    // then, in a single task, the ICE transports and the connection complete, and the candidates end
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    for (const auto &iceTransport: IceTransports()) {
      if (iceTransport->IsHeld()) {
        // Python doesn't have it yet: its completion waits along with its other events
        iceTransport->HeldGatheringComplete();
      } else {
        iceTransports.push_back(iceTransport);
      }
    }
    EmitGathering("_gatheringcomplete", iceTransports, new_state);
  }

  void RTCPeerConnection::HoldGathering() {
    std::lock_guard<std::mutex> lock(_gatheringMutex);
    _holdGathering = true;
  }

  void RTCPeerConnection::ReleaseGathering() {
    // emitted under the lock, so that events emitted meanwhile come after these
    std::lock_guard<std::mutex> lock(_gatheringMutex);
    for (auto &emit: _heldGathering) {
      emit();
    }
    _heldGathering.clear();
    _holdGathering = false;
  }

  std::vector<std::shared_ptr<RTCIceTransport>> RTCPeerConnection::WrapTransports() {
    std::vector<std::shared_ptr<RTCIceTransport>> created;
    auto pc = connection();
    if (!pc) {
      return created;
    }
    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> transports;
    for (const auto &transceiver: pc->GetTransceivers()) {
      transports.push_back(transceiver->sender()->dtls_transport());
      transports.push_back(transceiver->receiver()->dtls_transport());
    }
    if (auto sctp = pc->GetSctpTransport()) {
      transports.push_back(sctp->dtls_transport());
    }
    std::vector<std::shared_ptr<RTCDtlsTransport>> wrappers;
    for (const auto &transport: transports) {
      if (!transport) {
        continue;
      }
      bool existed = RTCDtlsTransport::holder().Find(transport.get()) != nullptr;
      auto wrapper = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);
      if (!existed) {
        // Python doesn't have the transports yet, their events wait for it
        wrapper->Hold();
        wrapper->GetIceTransport()->Hold();
        auto weak = weak_from_this();
        auto rawIce = transport->ice_transport();
        wrapper->GetIceTransport()->SetParametersGetter([weak, rawIce](bool local) {
          auto self = weak.lock();
          return self ? self->IceParameters(rawIce.get(), local) : std::nullopt;
        });
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

  std::shared_ptr<RTCIceTransport> RTCPeerConnection::IceTransportByMid(const std::string &mid) {
    auto pc = connection();
    auto dtls = pc && !mid.empty() ? pc->LookupDtlsTransportByMid(mid) : nullptr;
    auto wrapper = dtls ? RTCDtlsTransport::holder().Find(dtls.get()) : nullptr;
    return wrapper ? wrapper->GetIceTransport() : nullptr;
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
    // on the signaling thread, when a remote description is set
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
    std::optional<std::pair<std::string, std::string>> parameters;
    _factory->_signalingThread->BlockingCall([&]() {
      auto description = local ? pc->local_description() : pc->remote_description();
      if (!description) {
        return;
      }
      for (const auto &content: description->description()->contents()) {
        auto dtls = pc->LookupDtlsTransportByMid(content.mid());
        auto info = description->description()->GetTransportInfoByName(content.mid());
        if (dtls && dtls->ice_transport().get() == iceTransport && info) {
          parameters.emplace(info->description.ice_ufrag, info->description.ice_pwd);
          return;
        }
      }
    });
    return parameters;
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

  std::vector<std::shared_ptr<RTCIceTransport>> RTCPeerConnection::IceTransports() {
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    auto pc = connection();
    if (!pc) {
      return iceTransports;
    }
    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> dtlsTransports;
    for (const auto &transceiver: pc->GetTransceivers()) {
      dtlsTransports.push_back(transceiver->sender()->dtls_transport());
      dtlsTransports.push_back(transceiver->receiver()->dtls_transport());
    }
    if (auto sctp = pc->GetSctpTransport()) {
      dtlsTransports.push_back(sctp->dtls_transport());
    }
    for (const auto &transport: dtlsTransports) {
      auto dtls = transport ? RTCDtlsTransport::holder().Find(transport.get()) : nullptr;
      auto ice = dtls ? dtls->GetIceTransport() : nullptr;
      if (ice && std::find(iceTransports.begin(), iceTransports.end(), ice) == iceTransports.end()) {
        iceTransports.push_back(ice);
      }
    }
    return iceTransports;
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

  void RTCPeerConnection::OnIceCandidateError(const std::string &address, int port, const std::string &url, int error_code,
                                              const std::string &error_text) {
    Emit("icecandidateerror", address, port, url, error_code, error_text);
  }

  void RTCPeerConnection::OnRenegotiationNeeded() {
    // the legacy event, negotiationneeded is fired by OnNegotiationNeededEvent
  }

  void RTCPeerConnection::OnNegotiationNeededEvent(uint32_t event_id) {
    // Python asks ShouldFireNegotiationNeededEvent when delivering it, as the spec requires
    Emit("negotiationneeded", event_id);
  }

  void RTCPeerConnection::GetStats(std::function<void(std::string)> &onSuccess,
                                   std::function<void(RTCCallbackException)> &onFailure) {
    auto pc = statsConnection();
    if (!pc) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection is closed"));
      return;
    }
    // libwebrtc reuses a report for 50 ms, the stats are the current ones
    pc->ClearStatsCache();
    pc->GetStats(webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess).get());
  }

  bool RTCPeerConnection::ShouldFireNegotiationNeededEvent(uint32_t eventId) {
    auto pc = connection();
    return pc && pc->ShouldFireNegotiationNeededEvent(eventId);
  }

  void RTCPeerConnection::OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) {
    // the channel holds its events until Python has delivered this one, if it's going to
    auto channel = Wrap(_channels, data_channel);
    channel->OnAnnounced();
    if (!HasListeners()) {
      channel->Release();
    }
    Emit("datachannel", channel);
  }

  std::shared_ptr<RTCDataChannel> RTCPeerConnection::CreateDataChannel(
      const std::string &label, bool ordered, std::optional<int> maxPacketLifeTime, std::optional<int> maxRetransmits,
      const std::string &protocol, bool negotiated, std::optional<int> id, std::optional<int> priority) {
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection's signalingState is 'closed'.");
    }

    webrtc::DataChannelInit init;
    init.ordered = ordered;
    init.maxRetransmitTime = maxPacketLifeTime;
    init.maxRetransmits = maxRetransmits;
    init.protocol = protocol;
    init.negotiated = negotiated;
    init.id = id.value_or(-1);
    if (priority) {
      init.priority = webrtc::PriorityValue(static_cast<uint16_t>(*priority));
    }

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

  void RTCPeerConnection::OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) {

  }

  void RTCPeerConnection::OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                                     const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) {

  }

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

  void RTCPeerConnection::EmitTrack(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver) {
    auto wrapper = Wrap(_transceivers, transceiver);
    auto receiver = Wrap(_receivers, transceiver->receiver());
    std::vector<std::shared_ptr<MediaStream>> streams;
    for (const auto &stream: transceiver->receiver()->streams()) {
      streams.push_back(MediaStream::holder().GetOrCreate(_factory, stream));
    }
    Emit("track", wrapper, receiver, streams);
  }

  static std::vector<std::string> RemoteStreamIds(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver) {
    std::vector<std::string> ids;
    for (const auto &stream: transceiver->receiver()->streams()) {
      ids.push_back(stream->id());
    }
    return ids;
  }

  void RTCPeerConnection::SnapshotRemoteStreams(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
    std::map<const void *, std::vector<std::string>> before;
    for (const auto &transceiver: pc->GetTransceivers()) {
      before[transceiver.get()] = RemoteStreamIds(transceiver);
    }
    std::lock_guard<std::mutex> lock(_remoteStreamsMutex);
    _remoteStreamsBefore = std::move(before);
    _trackFired.clear();
  }

  void RTCPeerConnection::FireRemoteStreamChanges() {
    // on the signaling thread, when a remote description is set
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
      if (RemoteStreamIds(transceiver) != previous->second) {
        EmitTrack(transceiver);
      }
    }
  }

  void RTCPeerConnection::AddIceCandidate(
      std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
      const std::string &candidate, const std::optional<std::string> &sdpMid, std::optional<int> sdpMLineIndex,
      const std::optional<std::string> &usernameFragment) {
    auto pc = connection();
    if (!pc) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'addIceCandidate' on 'RTCPeerConnection': The RTCPeerConnection's signalingState is 'closed'."));
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

    if (IsBlockedCandidate(iceCandidate->candidate())) {
      onSuccess();
      return;
    }

    auto weak = weak_from_this();
    auto added = std::make_shared<IceCandidateInit>(*iceCandidate);
    pc->AddIceCandidate(std::move(iceCandidate), [weak, onSuccess, onFailure, added](webrtc::RTCError error) {
      if (error.ok()) {
        // the remote description has the candidate now
        if (auto self = weak.lock()) {
          self->RecordRemoteCandidate(*added);
          self->RefreshDescriptions();
          ReleaseElsewhere(std::move(self));
        }
        onSuccess();
      } else {
        onFailure(wrapRTCErrorForCallback(error));
      }
    });
  }

} // namespace python_webrtc
