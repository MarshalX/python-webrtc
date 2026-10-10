//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_ICE_TRANSPORT_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_ICE_TRANSPORT_H_

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include <api/ice_transport_interface.h>
#include <p2p/base/ice_transport_internal.h>

#include "../enums/enums.h"
#include "../models/python_webrtc/rtc_configuration.h"
#include "../models/python_webrtc/rtc_ice_candidate.h"
#include "../utils/held_events.h"
#include "../utils/locked_function.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "../utils/surfaced.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // What gathers the candidates of a transport Python creates (see RTCIceTransport::CreateStandalone)
  struct StandaloneIce;

  class RTCIceTransport : public NativeObject<RTCIceTransport>, public Emitter<RTCIceTransport> {
  public:
    static constexpr const char *kName = "RTCIceTransport";

    explicit RTCIceTransport(std::shared_ptr<PeerConnectionFactory> factory,
                             webrtc::scoped_refptr<webrtc::IceTransportInterface> transport);

    ~RTCIceTransport();

    RTCIceTransport(const RTCIceTransport &) = delete;
    RTCIceTransport &operator=(const RTCIceTransport &) = delete;

    static void Init(pybind11::module &m);

    static Registry<RTCIceTransport, webrtc::IceTransportInterface> &registry();

    RTCIceComponent GetComponent();

    webrtc::IceGatheringState GetGatheringState();

    // unknown until an answer (or a provisional one) is applied, as libwebrtc sets it with the offer
    webrtc::IceRole GetRole();

    webrtc::IceTransportState GetState();

    // the local and the remote candidate of the pair in use, and whether the remote one is peer-reflexive (known
    // from connectivity checks only, not signaled)
    std::optional<std::tuple<IceCandidateInit, IceCandidateInit, bool>> GetSelectedCandidatePair();

    std::vector<IceCandidateInit> GetLocalCandidates();

    std::vector<IceCandidateInit> GetRemoteCandidates();

    // the username fragment and the password
    std::optional<std::pair<std::string, std::string>> GetLocalParameters();

    std::optional<std::pair<std::string, std::string>> GetRemoteParameters();

    // see Surfaced
    void SurfaceState(webrtc::IceTransportState state);

    void SurfaceGatheringState(webrtc::IceGatheringState state);

    // The transport of a connection, which tells it about the descriptions and the candidates:

    void OnRTCDtlsTransportStopped();

    void OnDropped();

    // closed without an event
    void OnPeerConnectionClosed();

    // the role is known once an answer is applied
    void SetRoleKnown();

    // emits selectedcandidatepairchange if the selected pair changed, on any thread
    void CheckSelectedCandidatePair();

    // A description created the transport, which started gathering before the wrapper existed: Python sees it new,
    // then the change to gathering as an event
    void CreatedByDescription();

    // the completion of gathering, for a transport Python doesn't have yet
    void EmitGatheringComplete();

    // The candidates the connection gathered for the transport and sent in icecandidate events, and the ones the
    // remote peer signaled (in its description or with addIceCandidate)
    void AddLocalCandidate(const IceCandidateInit &candidate);

    void AddRemoteCandidate(const IceCandidateInit &candidate);

    // the parameters of the local or the remote description
    using ParametersGetter = std::optional<std::pair<std::string, std::string>>(bool local);

    void SetParametersGetter(std::function<ParametersGetter> getter);

    // the connection emitting the state changes, false once it's gone
    using StateEmitter = bool(webrtc::IceTransportState previous, webrtc::IceTransportState state);

    void SetStateEmitter(std::function<StateEmitter> emitter);

    // not the surfaced one
    webrtc::IceTransportState GetCurrentState();

    // see Surfaced
    void StateChanged(bool bound, webrtc::IceTransportState previous);

    void EmitStateChange(webrtc::IceTransportState state);

    // events wait out a running description operation (see HeldOperationEvents)
    void Hold() { _held.Hold(); }

    void Release() { _held.Release(); }

    bool IsHeld() { return _held.IsHeld(); }

    // A transport of its own, not of a connection (the webrtc-ice extension): Python gathers its candidates,
    // gives it the remote parameters and candidates, and it connects:

    static std::shared_ptr<RTCIceTransport> CreateStandalone(const std::shared_ptr<PeerConnectionFactory> &factory);

    bool IsStandalone() { return _standalone != nullptr; }

    void Gather(webrtc::PeerConnectionInterface::IceTransportsType policy,
                const std::vector<IceServerInit> &iceServers);

    // the remote parameters (flushing the remote candidates if they changed) and the role
    void Start(const std::string &usernameFragment, const std::string &password, webrtc::IceRole role);

    void AddStandaloneRemoteCandidate(const std::string &candidate, const std::string &sdpMid, int sdpMLineIndex,
                                      const std::optional<std::string> &usernameFragment);

    // closes it, without an event
    void StopStandalone();

    // the state and the gathering state show their current values, as the methods of a transport of its own
    // change them synchronously
    void SurfaceCurrent();

    // an icecandidate event of a transport of its own was delivered
    void SurfaceLocalCandidate();

  private:
    struct StateChange {
      webrtc::IceTransportState previousState;
      webrtc::IceTransportState state;
      webrtc::IceGatheringState previousGatheringState;
      webrtc::IceGatheringState gatheringState;
    };

    template <typename... Args>
    void Emit(const char *name, const Args &...args) {
      _held.Emit([this, name, args...]() { Emitter::Emit(name, args...); });
    }

    // reads the states of the transport, on the network thread
    StateChange TakeSnapshot();

    void OnStateChanged(webrtc::IceTransportInternal * /*unused*/);

    void OnGatheringStateChanged(webrtc::IceTransportInternal * /*unused*/);

    void EmitState(webrtc::IceTransportState previous, webrtc::IceTransportState state);

    std::optional<std::pair<std::string, std::string>> GetParameters(bool local);

    // Libwebrtc hides the address of a peer-reflexive candidate: the remote peer may have signaled it since,
    // which is found by port and protocol
    std::optional<IceCandidateInit> FindSignaledCandidate(const webrtc::Candidate &candidate);

    bool Stopped();

    std::shared_ptr<PeerConnectionFactory> _factory;
    HeldEvents _held;

    // accessed on the network thread only
    webrtc::IceTransportInternal *_subscribed = nullptr;

    std::mutex _mutex;
    RTCIceComponent _component = RTCIceComponent::kRtp;
    webrtc::IceTransportState _state = webrtc::IceTransportState::kNew;
    webrtc::IceGatheringState _gatheringState = webrtc::IceGatheringState::kIceGatheringNew;
    // the gathering state stays as Python saw it
    bool _connectionClosed = false;
    bool _dropped = false;
    webrtc::IceRole _role = webrtc::IceRole::ICEROLE_UNKNOWN;
    bool _roleKnown = false;
    Surfaced<webrtc::IceTransportState> _surfacedState;
    Surfaced<webrtc::IceGatheringState> _surfacedGatheringState;
    // the selected pair seen last, as candidate-attributes
    std::string _selectedPair;
    std::vector<IceCandidateInit> _localCandidates;
    std::vector<IceCandidateInit> _remoteCandidates;
    LockedFunction<ParametersGetter> _parametersGetter;
    LockedFunction<StateEmitter> _stateEmitter;

    // a transport of its own
    std::shared_ptr<StandaloneIce> _standalone;
    std::optional<std::pair<std::string, std::string>> _localParameters;
    std::optional<std::pair<std::string, std::string>> _remoteParameters;
    // the role it started with (libwebrtc switches it on a role conflict)
    std::optional<webrtc::IceRole> _startedRole;
    bool _stopped = false;
    size_t _surfacedLocal = 0;

    webrtc::scoped_refptr<webrtc::IceTransportInterface> _transport;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_ICE_TRANSPORT_H_
