//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>
#include <array>
#include <atomic>
#include <map>
#include <set>
#include <unordered_map>

#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/functional.h>

#include "../exceptions.h"
#include "../utils/listeners.h"
#include "../models/python_webrtc/rtc_session_description.h"
#include "../models/python_webrtc/rtc_configuration.h"

#include "media_stream_track.h"
#include "media_stream.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_transceiver.h"
#include "rtc_sctp_transport.h"
#include "rtc_data_channel.h"

namespace webrtc {
  struct PeerConnectionDependencies;
}

namespace python_webrtc {

  class PeerConnectionFactory;

  class RTCPeerConnection
      : public webrtc::PeerConnectionObserver, public Listeners, public std::enable_shared_from_this<RTCPeerConnection> {
  public:
    explicit RTCPeerConnection(const std::optional<ConfigurationInit> &);

    static void Init(pybind11::module &m);

    ~RTCPeerConnection() override;

    void CreateOffer(
        std::function<void(RTCSessionDescription)> &, std::function<void(RTCCallbackException)> &,
        bool iceRestart, std::optional<bool> offerToReceiveAudio, std::optional<bool> offerToReceiveVideo,
        bool voiceActivityDetection);

    void CreateAnswer(
        std::function<void(RTCSessionDescription)> &, std::function<void(RTCCallbackException)> &,
        bool voiceActivityDetection);

    void SetLocalDescription(
        std::function<void()> &, std::function<void(RTCCallbackException)> &,
        const std::optional<RTCSessionDescriptionInit> &);

    void SetRemoteDescription(
        std::function<void()> &, std::function<void(RTCCallbackException)> &, const RTCSessionDescriptionInit &);

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>);

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &, const std::vector<MediaStream *> &);

    std::shared_ptr<RTCRtpTransceiver> AddTransceiver(
        webrtc::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    std::shared_ptr<RTCRtpTransceiver> AddTransceiver(
        MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    std::vector<std::shared_ptr<RTCRtpTransceiver>> GetTransceivers();

    std::vector<std::shared_ptr<RTCRtpSender>> GetSenders();

    std::vector<std::shared_ptr<RTCRtpReceiver>> GetReceivers();

    std::optional<std::shared_ptr<RTCSctpTransport>> GetSctp();

    void AddIceCandidate(
        std::function<void()> &, std::function<void(RTCCallbackException)> &, const std::string &candidate,
        const std::optional<std::string> &sdpMid, std::optional<int> sdpMLineIndex,
        const std::optional<std::string> &usernameFragment);

    bool ShouldFireNegotiationNeededEvent(uint32_t eventId);

    void GetStats(std::function<void(std::string)> &, std::function<void(RTCCallbackException)> &);

    std::shared_ptr<RTCDataChannel> CreateDataChannel(
        const std::string &label, bool ordered, std::optional<int> maxPacketLifeTime, std::optional<int> maxRetransmits,
        const std::string &protocol, bool negotiated, std::optional<int> id, std::optional<int> priority);

    void RestartIce();

    ConfigurationInit GetConfiguration();

    void SetConfiguration(const ConfigurationInit &);

    void RemoveTrack(RTCRtpSender &);

    void SaveLastSdp(const RTCSessionDescriptionInit &lastSdp);

    void Close();

    bool IsClosed() { return !connection(); }

    webrtc::PeerConnectionInterface::PeerConnectionState GetConnectionState();

    webrtc::PeerConnectionInterface::SignalingState GetSignalingState();

    webrtc::PeerConnectionInterface::IceConnectionState GetIceConnectionState();

    webrtc::PeerConnectionInterface::IceGatheringState GetIceGatheringState();

    std::shared_ptr<RTCSessionDescription> GetLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetRemoteDescription();

    std::shared_ptr<RTCSessionDescription> GetCurrentLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetCurrentRemoteDescription();

    std::shared_ptr<RTCSessionDescription> GetPendingLocalDescription();

    std::shared_ptr<RTCSessionDescription> GetPendingRemoteDescription();

    // A state that changed is only seen by Python once its event is delivered, like in a browser, where the attribute
    // and the event change in the same task. Without listeners there are no events and the current state is seen.
    void SurfaceState(const std::string &event, int state);

    // PeerConnectionObserver implementation.
    void OnSignalingChange(webrtc::PeerConnectionInterface::SignalingState new_state) override;

    void OnIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) override;

    void OnStandardizedIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) override;

    void OnConnectionChange(webrtc::PeerConnectionInterface::PeerConnectionState new_state) override;

    void OnIceGatheringChange(webrtc::PeerConnectionInterface::IceGatheringState new_state) override;

    void OnIceCandidate(const webrtc::IceCandidateInterface *candidate) override;

    void OnIceCandidateError(const std::string &address, int port, const std::string &url, int error_code,
                             const std::string &error_text) override;

    void OnRenegotiationNeeded() override;

    void OnNegotiationNeededEvent(uint32_t event_id) override;

    void OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) override;

    void OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                    const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) override;

    void OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;

    void OnIceSelectedCandidatePairChanged(const webrtc::CandidatePairChangeEvent &event) override;

    void OnRemoveTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver) override;

  private:
    enum class DescriptionKind { kLocal, kRemote, kCurrentLocal, kCurrentRemote, kPendingLocal, kPendingRemote };

    std::shared_ptr<RTCSessionDescription> GetDescription(DescriptionKind);

    // on the signaling thread
    void ReadDescription(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &, DescriptionKind,
                         const webrtc::SessionDescriptionInterface *&description,
                         std::optional<RTCSessionDescriptionInit> &init,
                         std::vector<const webrtc::SessionDescriptionInterface *> &current);

  public:
    // Descriptions as an operation or a signaling state change left them (on the signaling thread), shown once
    // Python resumes from the operation or gets the event (ApplySnapshot) until the next event that changes them:
    // later candidates come with their events
    uint64_t SnapshotDescriptions();

    // the snapshot taken when an operation completed, without an id
    void ApplySnapshot(std::optional<uint64_t> id);

    std::atomic<uint64_t> _completionSnapshot{0};

  private:
    // a description is the same object for as long as it's set, guarded by _descriptionsMutex
    std::mutex _descriptionsMutex;
    std::vector<std::pair<const webrtc::SessionDescriptionInterface *, std::shared_ptr<RTCSessionDescription>>>
        _descriptions;
    // Candidates are added to the local description as they're gathered, which Python only sees once their events
    // are delivered: the events that change descriptions bump the generation (see RefreshDescriptions)
    uint64_t _descriptionsGeneration = 0;
    struct DescriptionsSnapshot {
      // by DescriptionKind: the description and its init, or none
      std::array<std::pair<const webrtc::SessionDescriptionInterface *, std::optional<RTCSessionDescriptionInit>>, 6> kinds;
      std::vector<const webrtc::SessionDescriptionInterface *> current;
    };
    std::map<uint64_t, DescriptionsSnapshot> _snapshots;
    uint64_t _lastSnapshot = 0;
    std::optional<DescriptionsSnapshot> _shown;
    uint64_t _shownGeneration = 0;
    // media sections of the remote description the remote peer ended the candidates of
    std::mutex _remoteEndOfCandidatesMutex;
    std::set<std::string> _remoteEndOfCandidates;
    const webrtc::SessionDescriptionInterface *_remoteEndOfCandidatesDescription = nullptr;
    uint64_t _descriptionsCachedGeneration = 0;

  public:
    void RefreshDescriptions();

  private:

    Surfaced<webrtc::PeerConnectionInterface::SignalingState> _surfacedSignalingState;
    Surfaced<webrtc::PeerConnectionInterface::IceConnectionState> _surfacedIceConnectionState;
    Surfaced<webrtc::PeerConnectionInterface::IceGatheringState> _surfacedIceGatheringState;
    Surfaced<webrtc::PeerConnectionInterface::PeerConnectionState> _surfacedConnectionState;
    // the states libwebrtc reported last, on the signaling thread
    webrtc::PeerConnectionInterface::SignalingState _lastSignalingState =
        webrtc::PeerConnectionInterface::SignalingState::kStable;
    webrtc::PeerConnectionInterface::IceConnectionState _lastIceConnectionState =
        webrtc::PeerConnectionInterface::IceConnectionState::kIceConnectionNew;
    webrtc::PeerConnectionInterface::IceGatheringState _lastIceGatheringState =
        webrtc::PeerConnectionInterface::IceGatheringState::kIceGatheringNew;
    webrtc::PeerConnectionInterface::PeerConnectionState _lastConnectionState =
        webrtc::PeerConnectionInterface::PeerConnectionState::kNew;


    // Python threads may call close() concurrently with other methods (the GIL is released)
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> connection();

    template<typename T, typename U>
    using Wrappers = std::unordered_map<U *, std::shared_ptr<T>>;

    // the wrapper of a libwebrtc object of this connection, which the connection keeps while it's open
    template<typename T, typename U>
    std::shared_ptr<T> Wrap(Wrappers<T, U> &, webrtc::scoped_refptr<U>);

    // wrappers of the current objects of this connection; wrappers of the objects that are gone are released
    template<typename T, typename U>
    std::vector<std::shared_ptr<T>> Sync(Wrappers<T, U> &, const std::vector<webrtc::scoped_refptr<U>> &);

    // wrappers of the objects of a closed connection, which doesn't keep them (see ReleaseWrappers)
    template<typename T, typename U>
    std::vector<std::shared_ptr<T>> Unkept(const std::vector<webrtc::scoped_refptr<U>> &);

    void ReleaseWrappers();

    // the codecs negotiated for a sender (in the remote description) or a receiver (in the local one)
    std::vector<webrtc::RtpCodecParameters> NegotiatedCodecs(const void *senderOrReceiver, bool send);

    // the header extensions negotiated for a receiver (in the local description)
    std::vector<webrtc::RtpExtension> NegotiatedHeaderExtensions(const void *receiver);

    void Adopt(const std::shared_ptr<RTCRtpSender> &);

    void Adopt(const std::shared_ptr<RTCRtpReceiver> &);

    void Adopt(const std::shared_ptr<RTCRtpTransceiver> &);

    void Adopt(const std::shared_ptr<RTCDataChannel> &);

    // the maxMessageSize of the SCTP transport, from the descriptions until the transport knows it
    std::optional<double> MaxMessageSize();

    // other wrappers need nothing from the connection
    template<typename T>
    void Adopt(const std::shared_ptr<T> &) {}

    void EmitTrack(const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver);

  public:
    // The streams the remote peer associates its tracks with, before a remote description is set, and the track
    // events it caused: a track event also tells about a track associated with other streams (on the signaling thread)
    void SnapshotRemoteStreams(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &);

    void FireRemoteStreamChanges();

  private:
    std::mutex _gatheringMutex;
    bool _holdGathering = false;
    std::vector<std::function<void()>> _heldGathering;

    std::mutex _remoteStreamsMutex;
    std::map<const void *, std::vector<std::string>> _remoteStreamsBefore;
    std::set<const void *> _trackFired;

    // waits for the negotiationneeded event a change may have caused to be emitted
    void QueueNegotiationNeeded();

    // the transports of a closed connection fire no events
    void MuteTransports();

  public:
    // the ICE transports of the connection that Python has wrappers of
    std::vector<std::shared_ptr<RTCIceTransport>> IceTransports();

    // the roles of the ICE transports are known once an answer is applied (on the signaling thread)
    void MarkIceRolesKnown();

    // Candidates and gathering state changes are held while a local description is set, and emitted once it's set
    void HoldGathering();

    void ReleaseGathering();

    template<typename... Args>
    void EmitGathering(const char *name, Args... args) {
      {
        std::lock_guard<std::mutex> lock(_gatheringMutex);
        if (_holdGathering) {
          _heldGathering.emplace_back([this, name, args...]() { Emit(name, args...); });
          return;
        }
      }
      Emit(name, std::move(args)...);
    }

    // the ICE transport a media section uses (on the signaling thread)
    std::shared_ptr<RTCIceTransport> IceTransportByMid(const std::string &mid);

    // the remote candidates of the ICE transports: added, or in the remote description
    void RecordRemoteCandidate(const IceCandidateInit &candidate);

    void RecordRemoteDescriptionCandidates();

    // the username fragment and the password of an ICE transport in the local or the remote description
    std::optional<std::pair<std::string, std::string>> IceParameters(
        const webrtc::IceTransportInterface *iceTransport, bool local);

    // Wraps the transports of the connection as soon as a description creates them, so that their states are
    // followed from the start, like in a browser, where they exist from then on. On the signaling thread.
    // Returns the ICE transports it created, which get their gathering event once the description is set.
    std::vector<std::shared_ptr<RTCIceTransport>> WrapTransports();

  private:
    std::vector<std::shared_ptr<RTCDtlsTransport>> _dtlsTransports;

    // declared first to be destroyed last, everything else is bound to its threads
    std::shared_ptr<PeerConnectionFactory> _factory;

    std::mutex _connectionMutex;

//    someStructWith2FieldMinAndMax _port_range;
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _jinglePeerConnection;
    // a closed connection still has stats, guarded by _connectionMutex
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _closedConnection;

  public:
    // the connection, even closed, to collect stats
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> statsConnection();

  private:

    RTCSessionDescriptionInit _lastSdp;

    // the last descriptions createOffer and createAnswer made, which are the only ones setLocalDescription takes
    std::mutex _lastSdpMutex;
    std::string _lastOffer;
    std::string _lastAnswer;

    // as it was set, guarded by _connectionMutex
    ConfigurationInit _configuration;

    std::mutex _wrappersMutex;
    Wrappers<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> _transceivers;
    Wrappers<RTCRtpSender, webrtc::RtpSenderInterface> _senders;
    Wrappers<RTCRtpReceiver, webrtc::RtpReceiverInterface> _receivers;
    std::shared_ptr<RTCSctpTransport> _sctp;
    // channels are kept while the connection is open, so their handlers are
    Wrappers<RTCDataChannel, webrtc::DataChannelInterface> _channels;
  };

}
