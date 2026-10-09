//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_RTC_PEER_CONNECTION_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_RTC_PEER_CONNECTION_H_

#include <array>
#include <atomic>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>

#include "../../exceptions.h"
#include "../../models/python_webrtc/rtc_configuration.h"
#include "../../models/python_webrtc/rtc_session_description.h"
#include "../../utils/alive_count.h"
#include "../../utils/held_events.h"
#include "../../utils/listeners.h"
#include "../../utils/surfaced.h"

#include "../media_stream.h"
#include "../media_stream_track.h"
#include "../rtc_data_channel.h"
#include "../rtc_rtp_sender.h"
#include "../rtc_rtp_transceiver.h"
#include "../rtc_sctp_transport.h"

namespace webrtc {
  struct PeerConnectionDependencies;
}

namespace python_webrtc {

  class PeerConnectionFactory;

  // An operation that completes after close() fails, rather than never settling as in a browser, which would
  // leave a Python caller waiting forever.
  class RTCPeerConnection : public webrtc::PeerConnectionObserver,
                            public Listeners,
                            public std::enable_shared_from_this<RTCPeerConnection> {
  public:
    using SignalingState = webrtc::PeerConnectionInterface::SignalingState;
    using IceConnectionState = webrtc::PeerConnectionInterface::IceConnectionState;
    using IceGatheringState = webrtc::PeerConnectionInterface::IceGatheringState;
    using PeerConnectionState = webrtc::PeerConnectionInterface::PeerConnectionState;

    explicit RTCPeerConnection(const std::optional<ConfigurationInit> &init);

    static void Init(pybind11::module &m);

    ~RTCPeerConnection() override;

    RTCPeerConnection(const RTCPeerConnection &) = delete;
    RTCPeerConnection &operator=(const RTCPeerConnection &) = delete;

    // A reference taken in a callback of libwebrtc, released on a thread of its own: the connection can't be
    // destroyed on the signaling thread in the middle of its own callback
    static void ReleaseElsewhere(std::shared_ptr<RTCPeerConnection> &&connection);

    void CreateOffer(std::function<void(RTCSessionDescription)> &onSuccess,
                     std::function<void(RTCCallbackException)> &onFailure, bool iceRestart);

    void CreateAnswer(std::function<void(RTCSessionDescription)> &onSuccess,
                      std::function<void(RTCCallbackException)> &onFailure);

    // for the fingerprint check of setLocalDescription
    void SaveCreatedDescription(const RTCSessionDescriptionInit &description);

    void SetLocalDescription(std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
                             const std::optional<RTCSessionDescriptionInit> &init);

    void SetRemoteDescription(std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
                              const RTCSessionDescriptionInit &init);

    void AddIceCandidate(std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
                         const std::string &candidate, const std::optional<std::string> &sdpMid,
                         std::optional<int> sdpMLineIndex, const std::optional<std::string> &usernameFragment);

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &mediaStreamTrack,
                                           std::optional<std::reference_wrapper<MediaStream>> mediaStream);

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &mediaStreamTrack,
                                           const std::vector<MediaStream *> &mediaStreams);

    void RemoveTrack(RTCRtpSender &sender);

    std::shared_ptr<RTCRtpTransceiver>
    AddTransceiver(webrtc::MediaType kind, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init);

    std::shared_ptr<RTCRtpTransceiver>
    AddTransceiver(MediaStreamTrack &track, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &init);

    std::vector<std::shared_ptr<RTCRtpTransceiver>> GetTransceivers();

    std::vector<std::shared_ptr<RTCRtpSender>> GetSenders();

    std::vector<std::shared_ptr<RTCRtpReceiver>> GetReceivers();

    std::shared_ptr<RTCDataChannel> CreateDataChannel(const std::string &label, bool ordered,
                                                      std::optional<int> maxPacketLifeTime,
                                                      std::optional<int> maxRetransmits, const std::string &protocol,
                                                      bool negotiated, std::optional<int> id,
                                                      webrtc::Priority priority);

    std::optional<std::shared_ptr<RTCSctpTransport>> GetSctp();

    void GetStats(std::function<void(std::string)> &onSuccess, std::function<void(RTCCallbackException)> &onFailure);

    void RestartIce();

    ConfigurationInit GetConfiguration();

    void SetConfiguration(const ConfigurationInit &init);

    void Close();

    PeerConnectionState GetConnectionState();

    SignalingState GetSignalingState();

    IceConnectionState GetIceConnectionState();

    IceGatheringState GetIceGatheringState();

    std::shared_ptr<RTCSessionDescription> GetLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetRemoteDescription();

    std::shared_ptr<RTCSessionDescription> GetCurrentLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetCurrentRemoteDescription();

    std::shared_ptr<RTCSessionDescription> GetPendingLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetPendingRemoteDescription();

    std::optional<bool> GetCanTrickleIceCandidates();

    // Python asks it when delivering a negotiationneeded event
    bool ShouldFireNegotiationNeededEvent(uint32_t eventId);

    // see Surfaced
    void SurfaceSignalingState(SignalingState state);

    void SurfaceIceConnectionState(IceConnectionState state);

    void SurfaceIceGatheringState(IceGatheringState state);

    void SurfaceConnectionState(PeerConnectionState state);

    // Shows the descriptions as an operation or a signaling state change left them (see SnapshotDescriptions),
    // once Python resumes from the operation (without a snapshot) or delivers the event
    void ApplyDescriptions(std::optional<uint64_t> snapshot);

    // Candidates are added to the local description as they're gathered, which Python only sees once their events
    // are delivered: these events refresh the descriptions
    void RefreshDescriptions();

    // the connection of a sender, bound here as the sender is bound before the connection
    static std::optional<std::shared_ptr<RTCPeerConnection>> ConnectionOf(RTCRtpSender &sender);

    // For the senders, receivers and transceivers of the connection:

    bool IsClosed();

    // the transceiver of a sender, while it's in the connection
    webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>
    TransceiverOf(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender);

    // The negotiated codecs this side can use: libwebrtc reports none for an inactive sender (receiver), and
    // lists remote codecs it doesn't know
    std::vector<webrtc::RtpCodecParameters>
    NegotiatedCodecs(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender);

    std::vector<webrtc::RtpCodecParameters>
    NegotiatedCodecs(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver);

    // the header extensions negotiated for a receiver (in the local description)
    std::vector<webrtc::RtpExtension>
    NegotiatedHeaderExtensions(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver);

    void CollectStats(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender,
                      std::function<void(std::string)> &onSuccess,
                      std::function<void(RTCCallbackException)> &onFailure);

    void CollectStats(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver,
                      std::function<void(std::string)> &onSuccess,
                      std::function<void(RTCCallbackException)> &onFailure);

    // PeerConnectionObserver implementation, on the signaling thread.
    void OnSignalingChange(SignalingState newState) override;

    void OnIceConnectionChange(IceConnectionState newState) override;

    void OnStandardizedIceConnectionChange(IceConnectionState newState) override;

    void OnConnectionChange(PeerConnectionState newState) override;

    void OnIceGatheringChange(IceGatheringState newState) override;

    void OnIceCandidate(const webrtc::IceCandidateInterface *candidate) override;

    void OnIceCandidateError(const std::string &address, int port, const std::string &url, int errorCode,
                             const std::string &errorText) override;

    void OnRenegotiationNeeded() override;

    void OnNegotiationNeededEvent(uint32_t eventId) override;

    void OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> dataChannel) override;

    void OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                    const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) override;

    void OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;

    void OnIceSelectedCandidatePairChanged(const webrtc::CandidatePairChangeEvent &event) override;

    void OnRemoveTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) override;

  private:
    // Holds the events a description operation causes (candidates, gathering and ICE states, ended tracks)
    // until it completes, so that they come after it
    class HeldOperationEvents;

    enum class DescriptionKind : uint8_t {
      kLocal,
      kRemote,
      kCurrentLocal,
      kCurrentRemote,
      kPendingLocal,
      kPendingRemote
    };

    static constexpr size_t kDescriptionKinds = 6;

    // a description of libwebrtc, and its SDP with what Python has seen of the candidates
    struct DescriptionView {
      const webrtc::SessionDescriptionInterface *description = nullptr;
      std::optional<RTCSessionDescriptionInit> init;
    };

    struct DescriptionsSnapshot {
      std::array<DescriptionView, kDescriptionKinds> kinds;
      // the descriptions set, which any of the kinds is
      std::vector<const webrtc::SessionDescriptionInterface *> live;
    };

    template <typename T, typename U>
    using Wrappers = std::unordered_map<U *, std::shared_ptr<T>>;

    // Python threads may call close() concurrently with other methods (the GIL is released)
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> connection();

    // a closed connection still has stats and transceivers
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> closedConnection();

    // The connection to collect the stats of, even closed, with its stats cache cleared: libwebrtc reuses a report
    // for 50 ms, the stats are the current ones. None fails the request.
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface>
    StatsConnection(const std::function<void(RTCCallbackException)> &onFailure);

    // the wrapper of a libwebrtc object of this connection, which the connection keeps while it's open
    template <typename T, typename U>
    std::shared_ptr<T> Wrap(Wrappers<T, U> &wrappers, webrtc::scoped_refptr<U> object);

    // wrappers of the current objects of this connection; wrappers of the objects that are gone are released
    template <typename T, typename U>
    std::vector<std::shared_ptr<T>> Sync(Wrappers<T, U> &wrappers,
                                         const std::vector<webrtc::scoped_refptr<U>> &objects);

    // wrappers of the objects of a closed connection, which doesn't keep them (see ReleaseWrappers)
    template <typename T, typename U>
    std::vector<std::shared_ptr<T>> Unkept(const std::vector<webrtc::scoped_refptr<U>> &objects);

    void ReleaseWrappers();

    // gives a wrapper what it needs from the connection
    void Adopt(const std::shared_ptr<RTCRtpSender> &sender);

    void Adopt(const std::shared_ptr<RTCRtpReceiver> &receiver);

    void Adopt(const std::shared_ptr<RTCRtpTransceiver> &transceiver);

    void Adopt(const std::shared_ptr<RTCDataChannel> &channel);

    void ForgetChannel(webrtc::DataChannelInterface *channel);

    void Adopt(const std::shared_ptr<RTCSctpTransport> &sctp);

    void Adopt(const std::shared_ptr<RTCDtlsTransport> &dtls);

    template <typename T>
    std::vector<webrtc::RtpCodecParameters> NegotiatedCodecsOf(const webrtc::scoped_refptr<T> &endpoint);

    // the maxMessageSize of the SCTP transport, from the descriptions until the transport knows it
    std::optional<double> MaxMessageSize();

    // waits for the negotiationneeded event a change may have caused to be emitted
    void QueueNegotiationNeeded();

    std::shared_ptr<RTCRtpTransceiver>
    AddedTransceiver(webrtc::RTCErrorOr<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>> result);

    // A provisional answer, or the final one after it, without SDP: the last answer createAnswer made, or a new one
    // (libwebrtc makes only final answers itself, and offers in have-local-pranswer)
    void SetImplicitAnswer(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc, webrtc::SdpType type,
                           std::function<void(webrtc::RTCError)> complete,
                           const std::function<void(RTCCallbackException)> &onFailure);

    // What completes setLocalDescription (kLocal) or setRemoteDescription (kRemote); created right before the
    // operation starts, as it holds its events
    std::function<void(webrtc::RTCError)> Completion(std::function<void()> &onSuccess,
                                                     std::function<void(RTCCallbackException)> &onFailure,
                                                     const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                                                     DescriptionKind kind);

    std::shared_ptr<RTCSessionDescription> GetDescription(DescriptionKind kind);

    // on the signaling thread
    DescriptionView ReadDescription(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                                    DescriptionKind kind);

    // the wrapper of a description that is set: the same object for as long as it's set, unless its SDP changed
    // meanwhile (refresh), under _descriptionsMutex
    std::shared_ptr<RTCSessionDescription>
    FindOrCreateDescription(const DescriptionView &view,
                            const std::vector<const webrtc::SessionDescriptionInterface *> &live, bool refresh);

    // The descriptions as an operation or event left them, shown from when Python gets it (see ApplyDescriptions).
    // On the signaling thread.
    uint64_t SnapshotDescriptions();

    // the ICE transports of the connection that Python has wrappers of
    std::vector<std::shared_ptr<RTCIceTransport>> IceTransports();

    // the ICE transport a media section uses, on the signaling thread
    std::shared_ptr<RTCIceTransport> IceTransportByMid(const std::string &mid);

    // Wraps the transports a description creates, so their states are followed from the start. Returns the new
    // ICE transports, which get their gathering event once the description is set. On the signaling thread.
    std::vector<std::shared_ptr<RTCIceTransport>> WrapTransports();

    // the transports of a closed connection fire no events
    void MuteTransports();

    // with the ICE connection state it changes, in one task; network thread
    template <typename T, typename State>
    void EmitTransportState(const std::shared_ptr<T> &transport, State previous, State state);

    // false if the connection or the transport is gone
    template <typename T, typename State>
    static bool EmitTransportStateOf(const std::weak_ptr<RTCPeerConnection> &connection,
                                     const std::weak_ptr<T> &transport, State previous, State state);

    // network thread
    void EmitIceConnectionState();

    // keeps Python off the network thread, which carries the media; deliveries stay in order
    void DeliverOnSignalingThread(std::function<void()> deliver);

    // the new state, if it changed
    std::optional<IceConnectionState> UpdateIceConnectionState(bool listening);

    // the roles of the ICE transports are known once an answer is applied, on the signaling thread
    void MarkIceRolesKnown();

    // the remote candidates of the ICE transports: added, or in the remote description (on the signaling thread)
    void RecordRemoteCandidate(const IceCandidateInit &candidate);

    void RecordRemoteDescriptionCandidates();

    // the username fragment and the password of an ICE transport in the local or the remote description
    std::optional<std::pair<std::string, std::string>> IceParameters(const webrtc::IceTransportInterface *iceTransport,
                                                                     bool local);

    // candidates and gathering state changes wait for the local description that caused them to be set
    template <typename... Args>
    void EmitGathering(const char *name, const Args &...args);

    void EmitTrack(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver);

    // The remote streams of each track before a remote description is set, to fire track events for tracks
    // moved to other streams. On the signaling thread.
    void SnapshotRemoteStreams(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc);

    void FireRemoteStreamChanges();

    // wrappers' destructors use the threads of the factory: declared first, to be destroyed last
    AliveCount<RTCPeerConnection> _counted;
    std::shared_ptr<PeerConnectionFactory> _factory;

    std::mutex _connectionMutex;
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _jinglePeerConnection;
    // a closed connection still has stats, guarded by _connectionMutex
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _closedConnection;
    // as it was set, guarded by _connectionMutex
    ConfigurationInit _configuration;

    std::mutex _createdMutex;
    std::string _lastOffer;
    std::string _lastAnswer;

    Surfaced<SignalingState> _surfacedSignalingState;
    Surfaced<IceConnectionState> _surfacedIceConnectionState;
    Surfaced<IceGatheringState> _surfacedIceGatheringState;
    Surfaced<PeerConnectionState> _surfacedConnectionState;
    // the states libwebrtc reported last, on the signaling thread
    SignalingState _lastSignalingState = SignalingState::kStable;
    IceGatheringState _lastIceGatheringState = IceGatheringState::kIceGatheringNew;
    std::mutex _connectionStatesMutex;
    IceConnectionState _lastIceConnectionState = IceConnectionState::kIceConnectionNew;
    PeerConnectionState _lastConnectionState = PeerConnectionState::kNew;

    std::mutex _descriptionsMutex;
    std::vector<std::pair<const webrtc::SessionDescriptionInterface *, std::shared_ptr<RTCSessionDescription>>>
        _descriptions;
    // bumped by the events that change descriptions (see RefreshDescriptions)
    uint64_t _descriptionsGeneration = 0;
    uint64_t _descriptionsCachedGeneration = 0;
    std::map<uint64_t, DescriptionsSnapshot> _snapshots;
    uint64_t _lastSnapshot = 0;
    std::optional<DescriptionsSnapshot> _shown;
    uint64_t _shownGeneration = 0;
    // the snapshot of the operation that completed last
    std::atomic<uint64_t> _completionSnapshot{0};

    // media sections of the remote description the remote peer ended the candidates of
    std::mutex _remoteEndOfCandidatesMutex;
    std::set<std::string> _remoteEndOfCandidates;
    const webrtc::SessionDescriptionInterface *_remoteEndOfCandidatesDescription = nullptr;

    HeldEvents _heldGathering;
    // held while a description is set
    HeldEvents _heldTransportStates;

    std::mutex _remoteStreamsMutex;
    std::map<const void *, std::vector<std::string>> _remoteStreamsBefore;
    std::set<const void *> _trackFired;

    std::mutex _wrappersMutex;
    Wrappers<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> _transceivers;
    Wrappers<RTCRtpSender, webrtc::RtpSenderInterface> _senders;
    Wrappers<RTCRtpReceiver, webrtc::RtpReceiverInterface> _receivers;
    std::shared_ptr<RTCSctpTransport> _sctp;
    std::vector<std::shared_ptr<RTCDtlsTransport>> _dtlsTransports;
    // in use at the last stable state; signaling thread
    std::vector<std::weak_ptr<RTCDtlsTransport>> _negotiatedTransports;
    // kept until closed, so their handlers are
    Wrappers<RTCDataChannel, webrtc::DataChannelInterface> _channels;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_RTC_PEER_CONNECTION_H_
