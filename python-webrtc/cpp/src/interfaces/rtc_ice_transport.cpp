//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_transport.h"

#include <algorithm>
#include <cstdint>
#include <utility>

#include <api/environment/environment_factory.h>
#include <p2p/base/p2p_constants.h>
#include <p2p/base/p2p_transport_channel.h>
#include <p2p/base/port_allocator.h>
#include <pc/ice_server_parsing.h>
#include <pc/ice_transport.h>
#include <rtc_base/crypto_random.h>

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"
#include "../utils/parking.h"
#include "../utils/port_allocator.h"

namespace python_webrtc {

  namespace {
    // what libwebrtc gives a connection's allocator, on the network thread
    std::unique_ptr<webrtc::PortAllocator> CreateStandalonePortAllocator(const webrtc::Environment &env,
                                                                         PeerConnectionFactory &factory) {
      auto allocator = CreatePortAllocator(env, factory.networkManager(), factory.packetSocketFactory(),
                                           /*tcpListen=*/false);
      allocator->Initialize();
      uint32_t flags =
          allocator->flags() | webrtc::PORTALLOCATOR_ENABLE_SHARED_SOCKET | webrtc::PORTALLOCATOR_ENABLE_IPV6_ON_WIFI;
      if (!env.field_trials().IsDisabled("WebRTC-IPv6Default")) {
        flags |= webrtc::PORTALLOCATOR_ENABLE_IPV6;
      }
      allocator->set_flags(flags);
      // no waits between gathering phases
      allocator->set_step_delay(0);
      allocator->SetNetworkIgnoreMask(factory.networkIgnoreMask());
      return allocator;
    }
  } // namespace

  // Owned by the transport, created and destroyed on the network thread, after the ICE transport that uses it
  struct StandaloneIce {
    explicit StandaloneIce(PeerConnectionFactory &factory)
        : env(webrtc::CreateEnvironment(factory.fieldTrials().CreateCopy())),
          allocator(CreateStandalonePortAllocator(env, factory)) {}

    ~StandaloneIce() {
      if (transport) {
        transport->Clear();
      }
      channel = nullptr;
    }

    StandaloneIce(const StandaloneIce &) = delete;
    StandaloneIce &operator=(const StandaloneIce &) = delete;

    webrtc::Environment env;
    std::unique_ptr<webrtc::PortAllocator> allocator;
    std::unique_ptr<webrtc::P2PTransportChannel> channel;
    webrtc::scoped_refptr<webrtc::IceTransportWithPointer> transport;
  };

  RTCIceTransport::RTCIceTransport(std::shared_ptr<PeerConnectionFactory> factory,
                                   webrtc::scoped_refptr<webrtc::IceTransportInterface> transport)
      : _factory(std::move(factory)), _transport(std::move(transport)) {
    BlockingCallOn(_factory->workerThread(), [this]() {
      auto *internal = _transport->internal();
      if (internal) {
        // state changes can't be unsubscribed from: guarded until the destructor disarms them
        internal->SubscribeIceTransportStateChanged(
            this, Guard([this](webrtc::IceTransportInternal *transport) { OnStateChanged(transport); }));
        internal->AddGatheringStateCallback(
            this, Guard([this](webrtc::IceTransportInternal *transport) { OnGatheringStateChanged(transport); }));
        _subscribed = internal;
      }
      TakeSnapshot(Pin::kNone);
    });
    // none until its first change, unless read unbound
    _surfacedPair.Changed(true, std::nullopt);
  }

  RTCIceTransport::~RTCIceTransport() {
    // callbacks run on the network thread, so after this none of them can be running or start again
    Disarm();
    BlockingCallOn(_factory->workerThread(), [this]() {
      // the internal transport is gone (with its callbacks) once the ice transport is cleared
      if (_subscribed && _transport->internal() == _subscribed) {
        _subscribed->RemoveGatheringStateCallback(this);
      }
      if (_standalone) {
        // on the network thread, before the factory whose network manager it shares
        _transport = nullptr;
        _standalone = nullptr;
      }
    });

    _transport = nullptr;
  }

  void RTCIceTransport::Init(pybind11::module &m) {
    DefineBinding(pybind11::class_<RTCIceTransport, Binding, std::shared_ptr<RTCIceTransport>>(m, "RTCIceTransport"))
        .def_property_readonly("_id", &RTCIceTransport::Id)
        // a transport of its own
        .def(pybind11::init(
            nogil_factory(+[]() { return CreateStandalone(PeerConnectionFactory::GetOrCreateDefault()); })))
        .def_property_readonly("component", nogil_fn(&RTCIceTransport::GetComponent))
        .def_property_readonly("gatheringState", nogil_fn(&RTCIceTransport::GetGatheringState))
        .def_property_readonly("role", nogil_fn(&RTCIceTransport::GetRole))
        .def_property_readonly("state", nogil_fn(&RTCIceTransport::GetState))
        .def("getSelectedCandidatePair", &RTCIceTransport::GetSelectedCandidatePair, nogil())
        .def("getLocalCandidates", &RTCIceTransport::GetLocalCandidates, nogil())
        .def("getRemoteCandidates", &RTCIceTransport::GetRemoteCandidates, nogil())
        .def("getLocalParameters", &RTCIceTransport::GetLocalParameters, nogil())
        .def("getRemoteParameters", &RTCIceTransport::GetRemoteParameters, nogil())
        .def("gather", &RTCIceTransport::Gather, nogil(), pybind11::arg("policy"), pybind11::arg("iceServers"))
        .def("start", &RTCIceTransport::Start, nogil(), pybind11::arg("usernameFragment"), pybind11::arg("password"),
             pybind11::arg("role"))
        .def("addRemoteCandidate", &RTCIceTransport::AddStandaloneRemoteCandidate, nogil(), pybind11::arg("candidate"),
             pybind11::arg("sdpMid"), pybind11::arg("sdpMLineIndex"), pybind11::arg("usernameFragment"))
        .def("stop", &RTCIceTransport::StopStandalone, nogil())
        .def_property_readonly("_standalone", &RTCIceTransport::IsStandalone)
        .def_property_readonly("_stopped", nogil_fn(&RTCIceTransport::Stopped))
        .def("_surfaceState", &RTCIceTransport::SurfaceState, nogil(), pybind11::arg("state"))
        .def("_surfaceSelectedPair", &RTCIceTransport::SurfaceSelectedPair, nogil(), pybind11::arg("pair"))
        .def("_surfaceGatheringState", &RTCIceTransport::SurfaceGatheringState, nogil(), pybind11::arg("state"))
        .def("_surfaceCandidate", &RTCIceTransport::SurfaceLocalCandidate, nogil());
  }

  Registry<RTCIceTransport, webrtc::IceTransportInterface> &RTCIceTransport::registry() {
    static ForkLocal<Registry<RTCIceTransport, webrtc::IceTransportInterface>> registry;
    return registry.Get();
  }

  RTCIceTransport::StateChange RTCIceTransport::TakeSnapshot(Pin pin) {
    std::unique_lock lock(_mutex);
    StateChange change{.previousState = _state,
                       .state = _state,
                       .previousGatheringState = _gatheringState,
                       .gatheringState = _gatheringState};
    if (_stopped || _connectionClosed || _dropped) {
      return change;
    }
    auto state = webrtc::IceTransportState::kClosed;
    auto gatheringState = webrtc::IceGatheringState::kIceGatheringComplete;
    auto *internal = _transport->internal();
    if (internal != nullptr) {
      _component = internal->component() == 1 ? RTCIceComponent::kRtp : RTCIceComponent::kRtcp;
      _role = internal->GetIceRole();
      state = internal->GetIceTransportState();
      if (_standalone && state == webrtc::IceTransportState::kNew && _remoteParameters && !_remoteCandidates.empty()) {
        // started with remote candidates: checking, as a transport of its own is from then on, even before it
        // has candidates to check them with
        state = webrtc::IceTransportState::kChecking;
      }
      gatheringState = internal->gathering_state();
    }

    if (pin == Pin::kState && state != _state) {
      _surfacedState.Changed(IsBound(), _state);
    }
    if (pin == Pin::kGatheringState && gatheringState != _gatheringState) {
      _surfacedGatheringState.Changed(IsBound(), _gatheringState);
    }
    _state = state;
    _gatheringState = gatheringState;

    change.state = _state;
    change.gatheringState = _gatheringState;
    lock.unlock();

    if (pin == Pin::kGatheringState && change.gatheringState != change.previousGatheringState) {
      Parking::At("ice.gatheringstatechange");
    }
    return change;
  }

  void RTCIceTransport::OnRTCDtlsTransportStopped() {
    webrtc::IceTransportState previous{};
    {
      const std::scoped_lock lock(_mutex);
      previous = _state;
      // ICE outlives a DTLS session the remote peer ended
      if (_transport->internal() != nullptr) {
        return;
      }
      if (previous != webrtc::IceTransportState::kClosed) {
        _surfacedState.Changed(IsBound(), previous);
      }
      _state = webrtc::IceTransportState::kClosed;
    }
    if (previous != webrtc::IceTransportState::kClosed) {
      // closed by a description (like the one bundling its media section on another transport), with its event;
      // a closed connection mutes its transports first, which are closed right away
      Parking::At("ice.closed");
      EmitState(previous, webrtc::IceTransportState::kClosed);
    }
  }

  void RTCIceTransport::OnDropped() {
    webrtc::IceTransportState previous{};
    {
      const std::scoped_lock lock(_mutex);
      previous = _state;
      if (previous != webrtc::IceTransportState::kClosed) {
        _surfacedState.Changed(IsBound(), previous);
      }
      _state = webrtc::IceTransportState::kClosed;
      _dropped = true;
    }
    if (previous != webrtc::IceTransportState::kClosed) {
      Parking::At("ice.closed");
      EmitState(previous, webrtc::IceTransportState::kClosed);
    }
  }

  void RTCIceTransport::OnPeerConnectionClosed() {
    Unbind();
    {
      const std::scoped_lock lock(_mutex);
      _gatheringState = _surfacedGatheringState.Get(_gatheringState);
      _state = webrtc::IceTransportState::kClosed;
      _connectionClosed = true;
    }
    _surfacedState.Reset();
    _surfacedGatheringState.Reset();
    _surfacedPair.Reset();
  }

  void RTCIceTransport::OnStateChanged(webrtc::IceTransportInternal * /*unused*/) {
    auto change = TakeSnapshot(Pin::kState);
    if (change.state == change.previousState) {
      return;
    }
    if (_standalone && change.state == webrtc::IceTransportState::kChecking) {
      // a transport of its own checks from start() or addRemoteCandidate() on, which change the state themselves
      _surfacedState.Surface(change.state);
      return;
    }
    if (_standalone) {
      // the pair it connects with first, then the state
      CheckSelectedCandidatePair();
    }
    EmitState(change.previousState, change.state);
  }

  void RTCIceTransport::EmitState(webrtc::IceTransportState previous, webrtc::IceTransportState state) {
    if (state == webrtc::IceTransportState::kFailed || state == webrtc::IceTransportState::kClosed) {
      const std::scoped_lock lock(_mutex);
      _selectedPair.reset();
    }
    auto emitter = _stateEmitter.Get();
    if (emitter && emitter(previous, state)) {
      return;
    }
    _surfacedState.Changed(IsBound(), previous);
    Emit("statechange", state);
  }

  void RTCIceTransport::OnGatheringStateChanged(webrtc::IceTransportInternal * /*unused*/) {
    auto change = TakeSnapshot(Pin::kGatheringState);
    auto current = change.gatheringState;
    if (current == change.previousGatheringState) {
      return;
    }
    if (_standalone) {
      // a transport of its own completes by itself, its candidates end first (gather() started gathering,
      // without an event)
      if (current == webrtc::IceGatheringState::kIceGatheringComplete) {
        Emit("icecandidate", std::optional<IceCandidateInit>());
        Emit("gatheringstatechange", current);
      }
    } else if (current != webrtc::IceGatheringState::kIceGatheringComplete) {
      // completion is emitted by the connection, along with its own (see RTCPeerConnection::OnIceGatheringChange)
      Emit("gatheringstatechange", current);
    }
  }

  RTCIceComponent RTCIceTransport::GetComponent() {
    const std::scoped_lock lock(_mutex);
    return _component;
  }

  webrtc::IceGatheringState RTCIceTransport::GetGatheringState() {
    webrtc::IceGatheringState state{};
    {
      const std::scoped_lock lock(_mutex);
      state = _gatheringState;
    }
    return _surfacedGatheringState.Shown(IsBound(), state);
  }

  webrtc::IceRole RTCIceTransport::GetRole() {
    {
      const std::scoped_lock lock(_mutex);
      if (!_roleKnown) {
        return webrtc::IceRole::ICEROLE_UNKNOWN;
      }
    }
    auto role = BlockingCallOn(_factory->workerThread(), [this]() {
      auto *internal = _transport ? _transport->internal() : nullptr;
      return internal ? internal->GetIceRole() : webrtc::IceRole::ICEROLE_UNKNOWN;
    });
    const std::scoped_lock lock(_mutex);
    // a closed transport has the last one
    if (role != webrtc::IceRole::ICEROLE_UNKNOWN) {
      _role = role;
    }
    return _role;
  }

  void RTCIceTransport::SetRoleKnown() {
    const std::scoped_lock lock(_mutex);
    _roleKnown = true;
  }

  webrtc::IceTransportState RTCIceTransport::GetState() {
    webrtc::IceTransportState state{};
    {
      const std::scoped_lock lock(_mutex);
      state = _state;
    }
    return _surfacedState.Shown(IsBound(), state);
  }

  std::optional<RTCIceTransport::CandidatePair> RTCIceTransport::GetSelectedCandidatePair() {
    {
      const std::scoped_lock lock(_mutex);
      if (_stopped) {
        return std::nullopt;
      }
    }
    return _surfacedPair.ShownOr(IsBound(), [this]() { return ReadSelectedCandidatePair(); });
  }

  std::optional<RTCIceTransport::CandidatePair> RTCIceTransport::ReadSelectedCandidatePair() {
    std::optional<CandidatePair> result;
    BlockingCallOn(_factory->workerThread(), [&]() {
      auto *internal = _transport ? _transport->internal() : nullptr;
      auto pair = internal ? internal->GetSelectedCandidatePair() : std::nullopt;
      if (!pair) {
        return;
      }
      // the transport is named after the media section it's negotiated in
      auto mid = internal->transport_name();
      auto local = webrtc::CreateIceCandidate(mid, 0, pair->local_candidate());
      auto remote = webrtc::CreateIceCandidate(mid, 0, pair->remote_candidate());
      auto signaled =
          pair->remote_candidate().is_prflx() ? FindSignaledCandidate(pair->remote_candidate()) : std::nullopt;
      const bool peerReflexive = pair->remote_candidate().is_prflx() && !signaled;
      result.emplace(IceCandidateInit(*local), signaled ? *signaled : IceCandidateInit(*remote), peerReflexive);
    });
    return result;
  }

  namespace {

    std::optional<IceCandidateInit> findSignaled(const std::vector<IceCandidateInit> &signaled,
                                                 const webrtc::Candidate &candidate) {
      for (const auto &known : signaled) {
        webrtc::SdpParseError error;
        auto parsed = webrtc::IceCandidate::Create(known.sdpMid, known.sdpMLineIndex, known.candidate, &error);
        if (parsed && parsed->candidate().address().port() == candidate.address().port() &&
            parsed->candidate().protocol() == candidate.protocol()) {
          return known;
        }
      }
      return std::nullopt;
    }

    void resolveSignaled(RTCIceTransport::CandidatePair &pair, const std::vector<IceCandidateInit> &signaled) {
      auto &[local, remote, peerReflexive] = pair;
      if (!peerReflexive) {
        return;
      }
      webrtc::SdpParseError error;
      auto parsed = webrtc::IceCandidate::Create(remote.sdpMid, remote.sdpMLineIndex, remote.candidate, &error);
      if (auto known = parsed ? findSignaled(signaled, parsed->candidate()) : std::nullopt) {
        remote = *known;
        peerReflexive = false;
      }
    }

  } // namespace

  std::optional<IceCandidateInit> RTCIceTransport::FindSignaledCandidate(const webrtc::Candidate &candidate) {
    const std::scoped_lock lock(_mutex);
    return findSignaled(_remoteCandidates, candidate);
  }

  std::vector<IceCandidateInit> RTCIceTransport::SignaledCandidates() {
    const std::scoped_lock lock(_mutex);
    return _remoteCandidates;
  }

  namespace {

    void addCandidate(std::vector<IceCandidateInit> &candidates, const IceCandidateInit &candidate) {
      if (candidate.candidate.empty()) {
        return;
      }
      for (const auto &known : candidates) {
        if (known.candidate == candidate.candidate) {
          return;
        }
      }
      candidates.push_back(candidate);
    }

  } // namespace

  void RTCIceTransport::AddLocalCandidate(const IceCandidateInit &candidate) {
    const std::scoped_lock lock(_mutex);
    addCandidate(_localCandidates, candidate);
  }

  void RTCIceTransport::AddRemoteCandidate(const IceCandidateInit &candidate) {
    std::vector<IceCandidateInit> signaled;
    {
      const std::scoped_lock lock(_mutex);
      addCandidate(_remoteCandidates, candidate);
      signaled = _remoteCandidates;
    }
    // copied: a Surfaced lock is a leaf
    _surfacedPair.Update([&signaled](std::optional<CandidatePair> &shown) {
      if (shown) {
        resolveSignaled(*shown, signaled);
      }
    });
  }

  std::vector<IceCandidateInit> RTCIceTransport::GetLocalCandidates() {
    const std::scoped_lock lock(_mutex);
    if (_standalone && IsBound()) {
      // the candidates of a transport of its own come with their events
      const auto surfaced = static_cast<std::ptrdiff_t>(std::min(_surfacedLocal, _localCandidates.size()));
      return {_localCandidates.begin(), _localCandidates.begin() + surfaced};
    }
    return _localCandidates;
  }

  void RTCIceTransport::SurfaceLocalCandidate() {
    const std::scoped_lock lock(_mutex);
    ++_surfacedLocal;
  }

  std::vector<IceCandidateInit> RTCIceTransport::GetRemoteCandidates() {
    const std::scoped_lock lock(_mutex);
    return _remoteCandidates;
  }

  void RTCIceTransport::SetParametersGetter(std::function<ParametersGetter> getter) {
    _parametersGetter.Set(std::move(getter));
  }

  void RTCIceTransport::SetStateEmitter(std::function<StateEmitter> emitter) {
    _stateEmitter.Set(std::move(emitter));
  }

  webrtc::IceTransportState RTCIceTransport::GetCurrentState() {
    const std::scoped_lock lock(_mutex);
    return _state;
  }

  void RTCIceTransport::StateChanged(bool bound, webrtc::IceTransportState previous) {
    _surfacedState.Changed(bound, previous);
  }

  void RTCIceTransport::EmitStateChange(webrtc::IceTransportState state) {
    Emit("statechange", state);
  }

  std::optional<std::pair<std::string, std::string>> RTCIceTransport::GetParameters(bool local) {
    {
      const std::scoped_lock lock(_mutex);
      if (_standalone) {
        return local ? _localParameters : _remoteParameters;
      }
    }
    auto getter = _parametersGetter.Get();
    return getter ? getter(local) : std::nullopt;
  }

  std::optional<std::pair<std::string, std::string>> RTCIceTransport::GetLocalParameters() {
    return GetParameters(true);
  }

  std::optional<std::pair<std::string, std::string>> RTCIceTransport::GetRemoteParameters() {
    return GetParameters(false);
  }

  std::shared_ptr<RTCIceTransport>
  RTCIceTransport::CreateStandalone(const std::shared_ptr<PeerConnectionFactory> &factory) {
    std::shared_ptr<StandaloneIce> standalone;
    webrtc::scoped_refptr<webrtc::IceTransportInterface> transport;
    std::pair<std::string, std::string> parameters(webrtc::CreateRandomString(webrtc::ICE_UFRAG_LENGTH),
                                                   webrtc::CreateRandomString(webrtc::ICE_PWD_LENGTH));
    BlockingCallOn(factory->workerThread(), [&]() {
      standalone = std::make_shared<StandaloneIce>(*factory);
      webrtc::IceTransportInit init(standalone->env);
      init.set_port_allocator(standalone->allocator.get());
      standalone->channel = webrtc::P2PTransportChannel::Create("", 1, std::move(init));
      standalone->transport = webrtc::make_ref_counted<webrtc::IceTransportWithPointer>(standalone->channel.get());
      transport = standalone->transport;
      transport->internal()->SetIceParameters(webrtc::IceParameters(parameters.first, parameters.second, false));
    });

    auto wrapper = registry().GetOrCreate(factory, transport);
    {
      const std::scoped_lock lock(wrapper->_mutex);
      wrapper->_standalone = std::move(standalone);
      wrapper->_localParameters = parameters;
    }
    BlockingCallOn(factory->workerThread(), [&]() {
      auto *internal = transport->internal();
      auto *self = wrapper.get();
      internal->SubscribeCandidateGathered(
          self, self->Guard([self](webrtc::IceTransportInternal *, const webrtc::Candidate &candidate) {
            if (self->Stopped()) {
              return;
            }
            IceCandidateInit init(*webrtc::CreateIceCandidate("", 0, candidate));
            self->AddLocalCandidate(init);
            self->Emit("icecandidate", std::optional<IceCandidateInit>(init));
          }));
      // both ends took the same role: the one told to switch does (RFC 8445 section 7.3.1.1)
      internal->SubscribeRoleConflict(self, self->Guard([self](webrtc::IceTransportInternal *transport) {
        if (!self->Stopped()) {
          transport->SetIceRole(transport->GetIceRole() == webrtc::ICEROLE_CONTROLLING ? webrtc::ICEROLE_CONTROLLED
                                                                                       : webrtc::ICEROLE_CONTROLLING);
        }
      }));
      internal->SetCandidatePairChangeCallback(
          self->Guard([self](const webrtc::CandidatePairChangeEvent &) { self->CheckSelectedCandidatePair(); }));
    });
    return wrapper;
  }

  void RTCIceTransport::Gather(webrtc::PeerConnectionInterface::IceTransportsType policy,
                               const std::vector<IceServerInit> &iceServers) {
    auto servers = toIceServers(iceServers);
    webrtc::RTCError error;
    BlockingCallOn(_factory->workerThread(), [&]() {
      webrtc::ServerAddresses stunServers;
      std::vector<webrtc::RelayServerConfig> turnServers;
      error = webrtc::ParseIceServersOrError(servers, &stunServers, &turnServers);
      if (!error.ok() || !_standalone) {
        return;
      }
      _standalone->allocator->SetConfiguration(stunServers, turnServers, 0, webrtc::NO_PRUNE);
      _standalone->allocator->SetCandidateFilter(policy == webrtc::PeerConnectionInterface::kRelay ? webrtc::CF_RELAY
                                                                                                   : webrtc::CF_ALL);
      _transport->internal()->MaybeStartGathering();
    });
    if (!error.ok()) {
      throw RTCException(error);
    }
    SurfaceCurrent();
  }

  void RTCIceTransport::Start(const std::string &usernameFragment, const std::string &password, webrtc::IceRole role) {
    bool changed = false;
    {
      const std::scoped_lock lock(_mutex);
      if (_startedRole && *_startedRole != role) {
        throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The transport started with another role");
      }
      _startedRole = role;
      const std::pair<std::string, std::string> parameters(usernameFragment, password);
      changed = _remoteParameters && *_remoteParameters != parameters;
      _remoteParameters = parameters;
      _roleKnown = true;
      if (changed) {
        _remoteCandidates.clear();
      }
    }
    BlockingCallOn(_factory->workerThread(), [&]() {
      auto *internal = _transport->internal();
      if (changed) {
        // the candidates were for the previous remote agent
        internal->RemoveAllRemoteCandidates();
      }
      internal->SetIceRole(role);
      internal->SetRemoteIceParameters(webrtc::IceParameters(usernameFragment, password, false));
    });
    SurfaceCurrent();
  }

  void RTCIceTransport::AddStandaloneRemoteCandidate(const std::string &candidate, const std::string &sdpMid,
                                                     int sdpMLineIndex,
                                                     const std::optional<std::string> &usernameFragment) {
    IceCandidateInit init(sdpMid, sdpMLineIndex, usernameFragment);
    init.candidate = candidate;
    webrtc::SdpParseError error;
    auto parsed = webrtc::IceCandidate::Create(sdpMid, sdpMLineIndex, candidate, &error);
    if (!parsed) {
      throw RTCException(webrtc::RTCErrorType::INTERNAL_ERROR,
                         "Failed to parse the ICE candidate: " + error.description);
    }
    AddRemoteCandidate(init);
    BlockingCallOn(_factory->workerThread(),
                   [&]() { _transport->internal()->AddRemoteCandidate(parsed->candidate()); });
    SurfaceCurrent();
  }

  bool RTCIceTransport::Stopped() {
    const std::scoped_lock lock(_mutex);
    return _stopped;
  }

  void RTCIceTransport::StopStandalone() {
    {
      const std::scoped_lock lock(_mutex);
      _stopped = true;
      _state = webrtc::IceTransportState::kClosed;
    }
    BlockingCallOn(_factory->workerThread(), [&]() { _transport->internal()->RemoveAllRemoteCandidates(); });
    Unbind();
    _surfacedState.Reset();
    _surfacedGatheringState.Reset();
    _surfacedPair.Reset();
  }

  void RTCIceTransport::SurfaceCurrent() {
    BlockingCallOn(_factory->workerThread(), [this]() { TakeSnapshot(Pin::kNone); });
    const std::scoped_lock lock(_mutex);
    _surfacedState.Surface(_state);
    _surfacedGatheringState.Surface(_gatheringState);
  }

  void RTCIceTransport::CreatedByDescription() {
    {
      const std::scoped_lock lock(_mutex);
      if (_gatheringState == webrtc::IceGatheringState::kIceGatheringNew) {
        return;
      }
    }
    _surfacedGatheringState.Surface(webrtc::IceGatheringState::kIceGatheringNew);
    Emit("gatheringstatechange", webrtc::IceGatheringState::kIceGatheringGathering);
  }

  void RTCIceTransport::EmitGatheringComplete() {
    Emit("gatheringstatechange", webrtc::IceGatheringState::kIceGatheringComplete);
  }

  namespace {

    std::string keyOf(const std::optional<RTCIceTransport::CandidatePair> &pair) {
      return pair ? std::get<0>(*pair).candidate + "|" + std::get<1>(*pair).candidate : std::string();
    }

  } // namespace

  void RTCIceTransport::CheckSelectedCandidatePair() {
    auto pair = ReadSelectedCandidatePair();
    {
      const std::scoped_lock lock(_mutex);
      if (keyOf(pair) == keyOf(_selectedPair)) {
        return;
      }
      if (pair) {
        _surfacedPair.Changed(IsBound(), _selectedPair);
      }
      _selectedPair = pair;
    }
    if (pair) {
      Parking::At("ice.pairchanged");
      Emit("selectedcandidatepairchange", *pair);
    }
  }

  void RTCIceTransport::SurfaceState(webrtc::IceTransportState state) {
    _surfacedState.Surface(state);
    if (state == webrtc::IceTransportState::kFailed || state == webrtc::IceTransportState::kClosed) {
      _surfacedPair.Surface(std::nullopt);
    }
  }

  void RTCIceTransport::SurfaceSelectedPair(std::optional<CandidatePair> pair) {
    if (pair) {
      resolveSignaled(*pair, SignaledCandidates());
    }
    _surfacedPair.Surface(std::move(pair));
  }

  void RTCIceTransport::SurfaceGatheringState(webrtc::IceGatheringState state) {
    _surfacedGatheringState.Surface(state);
  }

} // namespace python_webrtc
