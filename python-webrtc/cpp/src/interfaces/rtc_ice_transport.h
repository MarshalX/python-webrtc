//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include <api/ice_transport_interface.h>
#include <p2p/base/ice_transport_internal.h>

#include "../utils/listeners.h"
#include "../models/python_webrtc/rtc_ice_candidate.h"
#include "../models/python_webrtc/rtc_configuration.h"

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../enums/python_webrtc/rtc_ice_component.h"

namespace python_webrtc {

  // What gathers the candidates of a transport Python creates (see RTCIceTransport::CreateStandalone)
  struct StandaloneIce;

  class RTCIceTransport : public Listeners {
  public:
    explicit RTCIceTransport(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::IceTransportInterface>);

    ~RTCIceTransport();

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface> &holder();

    void OnRTCDtlsTransportStopped();

    RTCIceComponent GetComponent();

    webrtc::IceGatheringState GetGatheringState();

    // unknown until an answer (or a provisional one) is applied, as libwebrtc sets it with the offer
    webrtc::IceRole GetRole();

    void SetRoleKnown();

    webrtc::IceTransportState GetState();

    // the local and the remote candidate of the pair in use
    std::optional<std::pair<IceCandidateInit, IceCandidateInit>> GetSelectedCandidatePair();

    // emits selectedcandidatepairchange if the selected pair changed, on any thread
    void CheckSelectedCandidatePair();

    // A description created the transport, which started gathering before the wrapper existed: Python sees it new,
    // then the change to gathering as an event
    void CreatedByDescription();

    // the completion of gathering, for a transport Python doesn't have yet
    void HeldGatheringComplete();

    void SurfaceState(const std::string &event, int state);

    // The candidates the connection gathered for the transport and sent in icecandidate events, and the ones the
    // remote peer signaled (in its description or with addIceCandidate), recorded by the connection
    void AddLocalCandidate(const IceCandidateInit &candidate);

    void AddRemoteCandidate(const IceCandidateInit &candidate);

    std::vector<IceCandidateInit> GetLocalCandidates();

    std::vector<IceCandidateInit> GetRemoteCandidates();

    // the username fragment and the password of the local or the remote description, from the connection
    using ParametersGetter = std::function<std::optional<std::pair<std::string, std::string>>(bool local)>;

    void SetParametersGetter(ParametersGetter getter);

    std::optional<std::pair<std::string, std::string>> GetParameters(bool local);

    // A transport of its own, not of a connection (the webrtc-ice extension): Python gathers its candidates,
    // gives it the remote parameters and candidates, and it connects
    static std::shared_ptr<RTCIceTransport> CreateStandalone(const std::shared_ptr<PeerConnectionFactory> &factory);

    bool IsStandalone() { return _standalone != nullptr; }

    void Gather(bool relayOnly, const std::vector<IceServerInit> &iceServers);

    // the remote parameters (flushing the remote candidates if they changed) and the role
    void Start(const std::string &usernameFragment, const std::string &password, webrtc::IceRole role);

    void AddRemoteCandidateOf(const IceCandidateInit &candidate);

    // closes it, without an event
    void StopStandalone();

    // the state and the gathering state show their current values, as the methods of a transport of its own
    // change them synchronously
    void SurfaceCurrent();

    // an icecandidate event of a transport of its own was delivered
    void SurfaceLocalCandidate();

  protected:
    void Stop();

  public:
    // a closed connection fires no events of its transports, which show their current state
    void OnPeerConnectionClosed() {
      Mute();
      {
        // closing doesn't change the gathering state, which stays as Python saw it
        std::lock_guard<std::mutex> lock(_mutex);
        _gathering_state = _surfacedGatheringState.Get(_gathering_state);
        _gatheringFrozen = true;
      }
      _surfacedState.Reset();
      _surfacedGatheringState.Reset();
    }

  private:
    void OnStateChanged(webrtc::IceTransportInternal *);

    void OnGatheringStateChanged(webrtc::IceTransportInternal *);

    void TakeSnapshot();

    std::shared_ptr<PeerConnectionFactory> _factory;

    // Accessed on the network thread only. State change callbacks can't be unsubscribed from,
    // so they check this flag and become no-ops once the wrapper is gone.
    std::shared_ptr<bool> _alive = std::make_shared<bool>(true);
    webrtc::IceTransportInternal *_subscribed = nullptr;

    RTCIceComponent _component = RTCIceComponent::kRtp;
    webrtc::IceGatheringState _gathering_state = webrtc::IceGatheringState::kIceGatheringNew;
    std::mutex _mutex{};
    webrtc::IceRole _role = webrtc::IceRole::ICEROLE_UNKNOWN;
    bool _roleKnown = false;
    webrtc::IceTransportState _state = webrtc::IceTransportState::kNew;
    Surfaced<webrtc::IceTransportState> _surfacedState;
    Surfaced<webrtc::IceGatheringState> _surfacedGatheringState;
    // the selected pair seen last, as candidate-attributes
    std::string _selectedPair;
    std::vector<IceCandidateInit> _localCandidates;
    std::vector<IceCandidateInit> _remoteCandidates;
    ParametersGetter _parametersGetter;

    std::shared_ptr<StandaloneIce> _standalone;
    std::optional<std::pair<std::string, std::string>> _localParameters;
    std::optional<std::pair<std::string, std::string>> _remoteParameters;
    bool _stopped = false;
    bool _gatheringFrozen = false;
    size_t _surfacedLocal = 0;
    // the role the transport of its own started with (libwebrtc switches it on a role conflict)
    std::optional<webrtc::IceRole> _startedRole;
    webrtc::scoped_refptr<webrtc::IceTransportInterface> _transport;
  };

} // namespace python_webrtc
