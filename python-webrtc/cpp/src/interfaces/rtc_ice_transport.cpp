//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_transport.h"
#include "../utils/gil.h"
#include "../exceptions.h"

#include <api/environment/environment_factory.h>
#include <p2p/base/basic_packet_socket_factory.h>
#include <p2p/base/p2p_transport_channel.h>
#include <pc/ice_transport.h>
#include <p2p/base/p2p_constants.h>
#include <p2p/client/basic_port_allocator.h>
#include <pc/ice_server_parsing.h>
#include <rtc_base/crypto_random.h>
#include <rtc_base/network.h>

#include <pybind11/stl.h>

namespace python_webrtc {

  // Owned by the transport, created and destroyed on the network thread, after the ICE transport that uses it
  struct StandaloneIce {
    explicit StandaloneIce(webrtc::Thread *networkThread)
        : env(webrtc::CreateEnvironment()),
          networkManager(std::make_unique<webrtc::BasicNetworkManager>(env, networkThread->socketserver())),
          socketFactory(std::make_unique<webrtc::BasicPacketSocketFactory>(networkThread->socketserver())),
          allocator(std::make_unique<webrtc::BasicPortAllocator>(env, networkManager.get(), socketFactory.get())) {
      allocator->Initialize();
      // like the connections of the factory, which use every network (see PeerConnectionFactory)
      allocator->SetNetworkIgnoreMask(0);
    }

    ~StandaloneIce() {
      if (transport) {
        transport->Clear();
      }
      channel = nullptr;
    }

    webrtc::Environment env;
    std::unique_ptr<webrtc::BasicNetworkManager> networkManager;
    std::unique_ptr<webrtc::BasicPacketSocketFactory> socketFactory;
    std::unique_ptr<webrtc::BasicPortAllocator> allocator;
    std::unique_ptr<webrtc::P2PTransportChannel> channel;
    webrtc::scoped_refptr<webrtc::IceTransportWithPointer> transport;
  };

  RTCIceTransport::RTCIceTransport(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::IceTransportInterface> transport)
      : _factory(std::move(factory)), _transport(std::move(transport)) {
    _factory->_workerThread->BlockingCall([this]() {
      auto internal = _transport->internal();
      if (internal) {
        auto alive = _alive;
        internal->SubscribeIceTransportStateChanged(
            this, [this, alive](webrtc::IceTransportInternal *transport) {
              if (*alive) {
                OnStateChanged(transport);
              }
            });
        internal->AddGatheringStateCallback(
            this, [this, alive](webrtc::IceTransportInternal *transport) {
              if (*alive) {
                OnGatheringStateChanged(transport);
              }
            });
        _subscribed = internal;
      }
      TakeSnapshot();
      if (_state == webrtc::IceTransportState::kClosed) {
        Stop();
      }
    });
  }

  RTCIceTransport::~RTCIceTransport() {
    gil_release_if_held release;

    // callbacks run on the network thread, so after this none of them can be running or start again
    _factory->_workerThread->BlockingCall([this]() {
      *_alive = false;
      // the internal transport is gone (with its callbacks) once the ice transport is cleared
      if (_subscribed && _transport->internal() == _subscribed) {
        _subscribed->RemoveGatheringStateCallback(this);
      }
      if (_standalone) {
        // on the network thread, before what it uses
        _transport = nullptr;
        _standalone = nullptr;
      }
    });

    _transport = nullptr;
    DropListeners();
  }

  void RTCIceTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCIceTransport, std::shared_ptr<RTCIceTransport>> cls(
        m, "RTCIceTransport", Listeners::TypeSetup<RTCIceTransport>());
    Listeners::Bind(cls);
    cls.def("_surface", &RTCIceTransport::SurfaceState, nogil());
    cls.def("getSelectedCandidatePair", &RTCIceTransport::GetSelectedCandidatePair, nogil());
    cls.def("getLocalCandidates", &RTCIceTransport::GetLocalCandidates, nogil());
    cls.def("getRemoteCandidates", &RTCIceTransport::GetRemoteCandidates, nogil());
    cls.def("getLocalParameters", [](RTCIceTransport &self) { return self.GetParameters(true); }, nogil());
    cls.def("getRemoteParameters", [](RTCIceTransport &self) { return self.GetParameters(false); }, nogil());
    // a transport of its own
    cls.def(pybind11::init([]() { return CreateStandalone(PeerConnectionFactory::GetOrCreateDefault()); }), nogil());
    cls.def_property_readonly("_standalone", &RTCIceTransport::IsStandalone);
    cls.def("gather", &RTCIceTransport::Gather, nogil());
    cls.def("start", &RTCIceTransport::Start, nogil());
    cls.def("addRemoteCandidate", [](RTCIceTransport &self, const std::string &candidate, const std::string &sdpMid,
                                     int sdpMLineIndex, std::optional<std::string> usernameFragment) {
      IceCandidateInit init(sdpMid, sdpMLineIndex, std::move(usernameFragment));
      init.candidate = candidate;
      self.AddRemoteCandidateOf(init);
    }, nogil());
    cls.def("stop", &RTCIceTransport::StopStandalone, nogil());
    cls.def("_surfaceCandidate", &RTCIceTransport::SurfaceLocalCandidate, nogil());
    cls.def_property_readonly("component", nogil_fn(&RTCIceTransport::GetComponent))
        .def_property_readonly("gatheringState", nogil_fn(&RTCIceTransport::GetGatheringState))
        .def_property_readonly("role", nogil_fn(&RTCIceTransport::GetRole))
        .def_property_readonly("state", nogil_fn(&RTCIceTransport::GetState));
  }

  InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface> &RTCIceTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface>();
    return *holder;
  }

  void RTCIceTransport::TakeSnapshot() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_stopped) {
      return;
    }
    auto internal = _transport->internal();
    if (internal) {
      if (internal->component() == 1) {
        _component = RTCIceComponent::kRtp;
      } else {
        _component = RTCIceComponent::kRtcp;
      }

      _role = internal->GetIceRole();
      _state = internal->GetIceTransportState();
      if (_standalone && _state == webrtc::IceTransportState::kNew && _remoteParameters && !_remoteCandidates.empty()) {
        // started with remote candidates: checking, as a transport of its own is from then on, even before it
        // has candidates to check them with
        _state = webrtc::IceTransportState::kChecking;
      }
      if (!_gatheringFrozen) {
        _gathering_state = internal->gathering_state();
      }
    } else {
      _state = webrtc::IceTransportState::kClosed;
      if (!_gatheringFrozen) {
        _gathering_state = webrtc::IceGatheringState::kIceGatheringComplete;
      }
    }
  }

  void RTCIceTransport::OnRTCDtlsTransportStopped() {
    webrtc::IceTransportState previous;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      previous = _state;
      _state = webrtc::IceTransportState::kClosed;
      Stop();
    }
    if (previous != webrtc::IceTransportState::kClosed) {
      // closed by a description (like the one bundling its media section on another transport), with its event;
      // a closed connection mutes its transports first, which are closed right away
      _surfacedState.Changed(Tracked(), previous);
      Emit("statechange", static_cast<int>(webrtc::IceTransportState::kClosed));
    }
  }

  void RTCIceTransport::Stop() {

  }

  void RTCIceTransport::OnStateChanged(webrtc::IceTransportInternal *) {
    webrtc::IceTransportState previous, current;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      previous = _state;
    }
    TakeSnapshot();
    {
      std::lock_guard<std::mutex> lock(_mutex);
      current = _state;
    }

    if (current != previous && _standalone && current == webrtc::IceTransportState::kChecking) {
      // a transport of its own checks from start() or addRemoteCandidate() on, which change the state themselves
      _surfacedState.Surface(current);
    } else if (current != previous) {
      if (_standalone) {
        // the pair it connects with first, then the state
        CheckSelectedCandidatePair();
      }
      _surfacedState.Changed(Tracked(), previous);
      Emit("statechange", static_cast<int>(current));
    }

    if (_state == webrtc::IceTransportState::kClosed) {
      Stop();
    }
  }

  void RTCIceTransport::OnGatheringStateChanged(webrtc::IceTransportInternal *) {
    webrtc::IceGatheringState previous, current;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      previous = _gathering_state;
    }
    TakeSnapshot();
    {
      std::lock_guard<std::mutex> lock(_mutex);
      current = _gathering_state;
    }

    if (current != previous) {
      _surfacedGatheringState.Changed(Tracked(), previous);
      // completion is delivered by the connection, along with its own (see RTCPeerConnection::OnIceGatheringChange)
      if (_standalone) {
        // a transport of its own completes by itself, its candidates end first (gather() started gathering,
        // without an event)
        if (current == webrtc::IceGatheringState::kIceGatheringComplete) {
          Emit("icecandidate", std::optional<IceCandidateInit>());
          Emit("gatheringstatechange", static_cast<int>(current));
        }
      } else if (current != webrtc::IceGatheringState::kIceGatheringComplete) {
        Emit("gatheringstatechange", static_cast<int>(current));
      }
    }
  }

  RTCIceComponent RTCIceTransport::GetComponent() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_component == 1) {
      return RTCIceComponent::kRtp;
    } else {
      return RTCIceComponent::kRtcp;
    }
  }

  webrtc::IceGatheringState RTCIceTransport::GetGatheringState() {
    webrtc::IceGatheringState state;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      state = _gathering_state;
    }
    return _surfacedGatheringState.Get(state);
  }

  webrtc::IceRole RTCIceTransport::GetRole() {
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (!_roleKnown) {
        return webrtc::IceRole::ICEROLE_UNKNOWN;
      }
    }
    auto role = webrtc::IceRole::ICEROLE_UNKNOWN;
    _factory->_workerThread->BlockingCall([&]() {
      auto internal = _transport ? _transport->internal() : nullptr;
      if (internal) {
        role = internal->GetIceRole();
      }
    });
    if (role == webrtc::IceRole::ICEROLE_UNKNOWN) {
      // closed: the last one
      std::lock_guard<std::mutex> lock(_mutex);
      return _role;
    }
    std::lock_guard<std::mutex> lock(_mutex);
    _role = role;
    return role;
  }

  void RTCIceTransport::SetRoleKnown() {
    std::lock_guard<std::mutex> lock(_mutex);
    _roleKnown = true;
  }

  webrtc::IceTransportState RTCIceTransport::GetState() {
    webrtc::IceTransportState state;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      state = _state;
    }
    return _surfacedState.Get(state);
  }

  std::optional<std::pair<IceCandidateInit, IceCandidateInit>> RTCIceTransport::GetSelectedCandidatePair() {
    std::optional<std::pair<IceCandidateInit, IceCandidateInit>> result;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (_stopped) {
        return result;
      }
    }
    _factory->_workerThread->BlockingCall([&]() {
      auto internal = _transport ? _transport->internal() : nullptr;
      auto pair = internal ? internal->GetSelectedCandidatePair() : std::nullopt;
      if (!pair) {
        return;
      }
      // the transport is named after the media section it's negotiated in
      auto mid = internal->transport_name();
      auto local = webrtc::CreateIceCandidate(mid, 0, pair->local_candidate());
      auto remote = webrtc::CreateIceCandidate(mid, 0, pair->remote_candidate());
      result.emplace(IceCandidateInit(*local), IceCandidateInit(*remote));
      if (pair->remote_candidate().is_prflx()) {
        // a peer-reflexive candidate the remote peer signaled since is the signaled one (by port and protocol,
        // as libwebrtc hides the address of the peer-reflexive one)
        std::lock_guard<std::mutex> lock(_mutex);
        for (const auto &signaled: _remoteCandidates) {
          webrtc::SdpParseError error;
          auto parsed = webrtc::IceCandidate::Create(signaled.sdpMid, signaled.sdpMLineIndex, signaled.candidate, &error);
          if (parsed && parsed->candidate().address().port() == pair->remote_candidate().address().port() &&
              parsed->candidate().protocol() == pair->remote_candidate().protocol()) {
            result->second = signaled;
            break;
          }
        }
      }
    });
    return result;
  }

  static void AddCandidate(std::vector<IceCandidateInit> &candidates, const IceCandidateInit &candidate) {
    if (candidate.candidate.empty()) {
      return;
    }
    for (const auto &known: candidates) {
      if (known.candidate == candidate.candidate) {
        return;
      }
    }
    candidates.push_back(candidate);
  }

  void RTCIceTransport::AddLocalCandidate(const IceCandidateInit &candidate) {
    std::lock_guard<std::mutex> lock(_mutex);
    AddCandidate(_localCandidates, candidate);
  }

  void RTCIceTransport::AddRemoteCandidate(const IceCandidateInit &candidate) {
    std::lock_guard<std::mutex> lock(_mutex);
    AddCandidate(_remoteCandidates, candidate);
  }

  std::vector<IceCandidateInit> RTCIceTransport::GetLocalCandidates() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_standalone && HasListeners()) {
      // the candidates of a transport of its own come with their events
      return {_localCandidates.begin(), _localCandidates.begin() + std::min(_surfacedLocal, _localCandidates.size())};
    }
    return _localCandidates;
  }

  void RTCIceTransport::SurfaceLocalCandidate() {
    std::lock_guard<std::mutex> lock(_mutex);
    ++_surfacedLocal;
  }

  std::vector<IceCandidateInit> RTCIceTransport::GetRemoteCandidates() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _remoteCandidates;
  }

  void RTCIceTransport::SetParametersGetter(ParametersGetter getter) {
    std::lock_guard<std::mutex> lock(_mutex);
    _parametersGetter = std::move(getter);
  }

  std::optional<std::pair<std::string, std::string>> RTCIceTransport::GetParameters(bool local) {
    ParametersGetter getter;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (_standalone) {
        return local ? _localParameters : _remoteParameters;
      }
      getter = _parametersGetter;
    }
    return getter ? getter(local) : std::nullopt;
  }

  std::shared_ptr<RTCIceTransport> RTCIceTransport::CreateStandalone(
      const std::shared_ptr<PeerConnectionFactory> &factory) {
    std::shared_ptr<StandaloneIce> standalone;
    webrtc::scoped_refptr<webrtc::IceTransportInterface> transport;
    std::pair<std::string, std::string> parameters(
        webrtc::CreateRandomString(webrtc::ICE_UFRAG_LENGTH), webrtc::CreateRandomString(webrtc::ICE_PWD_LENGTH));
    factory->_workerThread->BlockingCall([&]() {
      standalone = std::make_shared<StandaloneIce>(factory->_workerThread.get());
      webrtc::IceTransportInit init(standalone->env);
      init.set_port_allocator(standalone->allocator.get());
      standalone->channel = webrtc::P2PTransportChannel::Create("", 1, std::move(init));
      standalone->transport = webrtc::make_ref_counted<webrtc::IceTransportWithPointer>(standalone->channel.get());
      transport = standalone->transport;
      transport->internal()->SetIceParameters(webrtc::IceParameters(parameters.first, parameters.second, false));
    });

    auto wrapper = holder().GetOrCreate(factory, transport);
    {
      std::lock_guard<std::mutex> lock(wrapper->_mutex);
      wrapper->_standalone = std::move(standalone);
      wrapper->_localParameters = parameters;
    }
    factory->_workerThread->BlockingCall([&]() {
      auto internal = transport->internal();
      auto alive = wrapper->_alive;
      auto *self = wrapper.get();
      internal->SubscribeCandidateGathered(
          self, [self, alive](webrtc::IceTransportInternal *, const webrtc::Candidate &candidate) {
            if (*alive) {
              IceCandidateInit init(*webrtc::CreateIceCandidate("", 0, candidate));
              self->AddLocalCandidate(init);
              self->Emit("icecandidate", std::optional<IceCandidateInit>(init));
            }
          });
      // both ends took the same role: the one told to switch does (RFC 8445 section 7.3.1.1)
      internal->SubscribeRoleConflict(self, [alive](webrtc::IceTransportInternal *transport) {
        if (*alive) {
          transport->SetIceRole(transport->GetIceRole() == webrtc::ICEROLE_CONTROLLING
                                ? webrtc::ICEROLE_CONTROLLED : webrtc::ICEROLE_CONTROLLING);
        }
      });
      internal->SetCandidatePairChangeCallback([self, alive](const webrtc::CandidatePairChangeEvent &) {
        if (*alive) {
          self->CheckSelectedCandidatePair();
        }
      });
    });
    return wrapper;
  }

  void RTCIceTransport::Gather(bool relayOnly, const std::vector<IceServerInit> &iceServers) {
    webrtc::PeerConnectionInterface::IceServers servers;
    for (const auto &server: iceServers) {
      webrtc::PeerConnectionInterface::IceServer iceServer;
      iceServer.urls = server.urls;
      iceServer.username = server.username.value_or("");
      iceServer.password = server.credential.value_or("");
      servers.push_back(std::move(iceServer));
    }
    webrtc::RTCError error;
    _factory->_workerThread->BlockingCall([&]() {
      webrtc::ServerAddresses stunServers;
      std::vector<webrtc::RelayServerConfig> turnServers;
      error = webrtc::ParseIceServersOrError(servers, &stunServers, &turnServers);
      if (!error.ok() || !_standalone) {
        return;
      }
      _standalone->allocator->SetConfiguration(stunServers, turnServers, 0, webrtc::NO_PRUNE);
      _standalone->allocator->SetCandidateFilter(relayOnly ? webrtc::CF_RELAY : webrtc::CF_ALL);
      _transport->internal()->MaybeStartGathering();
    });
    if (!error.ok()) {
      throw wrapRTCError(error);
    }
    SurfaceCurrent();
  }

  void RTCIceTransport::Start(const std::string &usernameFragment, const std::string &password, webrtc::IceRole role) {
    bool changed;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (_startedRole && *_startedRole != role) {
        throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The transport started with another role");
      }
      _startedRole = role;
      std::pair<std::string, std::string> parameters(usernameFragment, password);
      changed = _remoteParameters && *_remoteParameters != parameters;
      _remoteParameters = parameters;
      _roleKnown = true;
      if (changed) {
        _remoteCandidates.clear();
      }
    }
    _factory->_workerThread->BlockingCall([&]() {
      auto internal = _transport->internal();
      if (changed) {
        // the candidates were for the previous remote agent
        internal->RemoveAllRemoteCandidates();
      }
      internal->SetIceRole(role);
      internal->SetRemoteIceParameters(webrtc::IceParameters(usernameFragment, password, false));
    });
    SurfaceCurrent();
  }

  void RTCIceTransport::AddRemoteCandidateOf(const IceCandidateInit &candidate) {
    webrtc::SdpParseError error;
    auto parsed = webrtc::IceCandidate::Create(candidate.sdpMid, candidate.sdpMLineIndex, candidate.candidate, &error);
    if (!parsed) {
      throw RTCException(webrtc::RTCErrorType::INTERNAL_ERROR, "Failed to parse the ICE candidate: " + error.description);
    }
    AddRemoteCandidate(candidate);
    _factory->_workerThread->BlockingCall([&]() {
      _transport->internal()->AddRemoteCandidate(parsed->candidate());
    });
    SurfaceCurrent();
  }

  void RTCIceTransport::StopStandalone() {
    _factory->_workerThread->BlockingCall([&]() {
      // nothing more to connect with, and no more events
      *_alive = false;
      _transport->internal()->RemoveAllRemoteCandidates();
    });
    {
      std::lock_guard<std::mutex> lock(_mutex);
      _stopped = true;
      _state = webrtc::IceTransportState::kClosed;
    }
    Mute();
    _surfacedState.Reset();
    _surfacedGatheringState.Reset();
  }

  void RTCIceTransport::SurfaceCurrent() {
    _factory->_workerThread->BlockingCall([this]() { TakeSnapshot(); });
    std::lock_guard<std::mutex> lock(_mutex);
    _surfacedState.Surface(_state);
    _surfacedGatheringState.Surface(_gathering_state);
  }

  void RTCIceTransport::CreatedByDescription() {
    auto gathering = webrtc::IceGatheringState::kIceGatheringGathering;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (_gathering_state == webrtc::IceGatheringState::kIceGatheringNew) {
        return;
      }
    }
    _surfacedGatheringState.Surface(webrtc::IceGatheringState::kIceGatheringNew);
    Emit("gatheringstatechange", static_cast<int>(gathering));
  }

  void RTCIceTransport::HeldGatheringComplete() {
    Emit("gatheringstatechange", static_cast<int>(webrtc::IceGatheringState::kIceGatheringComplete));
  }

  void RTCIceTransport::CheckSelectedCandidatePair() {
    auto pair = GetSelectedCandidatePair();
    auto key = pair ? pair->first.candidate + "|" + pair->second.candidate : std::string();
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (key == _selectedPair) {
        return;
      }
      _selectedPair = key;
    }
    if (pair) {
      Emit("selectedcandidatepairchange");
    }
  }

  void RTCIceTransport::SurfaceState(const std::string &event, int state) {
    if (event == "statechange") {
      _surfacedState.Surface(static_cast<webrtc::IceTransportState>(state));
    } else {
      _surfacedGatheringState.Surface(static_cast<webrtc::IceGatheringState>(state));
    }
  }

} // namespace python_webrtc
