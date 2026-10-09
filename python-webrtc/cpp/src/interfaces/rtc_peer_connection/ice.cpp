//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"

#include <algorithm>
#include <utility>

#include <pc/session_description.h>

#include "../peer_connection_factory.h"
#include "sdp.h"

namespace python_webrtc {

  std::optional<bool> RTCPeerConnection::GetCanTrickleIceCandidates() {
    auto pc = connection();
    return pc ? pc->can_trickle_ice_candidates() : std::nullopt;
  }

  template <typename... Args>
  void RTCPeerConnection::EmitGathering(const char *name, const Args &...args) {
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
    for (auto &candidate : endOfCandidates(pc ? pc->local_description() : nullptr)) {
      EmitGathering("icecandidate", candidate);
    }
    // then, in a single task, the ICE transports and the connection complete, and the candidates end
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    for (const auto &iceTransport : IceTransports()) {
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
    if (candidate != nullptr) {
      const IceCandidateInit init(*candidate);
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

  namespace {

    // the DTLS transports of the media sections and of the data channels, some of them shared (bundled)
    std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>>
    dtlsTransports(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
      std::vector<webrtc::scoped_refptr<webrtc::DtlsTransportInterface>> transports;
      for (const auto &transceiver : pc->GetTransceivers()) {
        transports.push_back(transceiver->sender()->dtls_transport());
        transports.push_back(transceiver->receiver()->dtls_transport());
      }
      if (auto sctp = pc->GetSctpTransport()) {
        transports.push_back(sctp->dtls_transport());
      }
      std::erase(transports, nullptr);
      return transports;
    }

  } // namespace

  std::vector<std::shared_ptr<RTCIceTransport>> RTCPeerConnection::IceTransports() {
    std::vector<std::shared_ptr<RTCIceTransport>> iceTransports;
    auto pc = connection();
    if (!pc) {
      return iceTransports;
    }
    for (const auto &transport : dtlsTransports(pc)) {
      auto dtls = RTCDtlsTransport::holder().Find(transport.get());
      auto ice = dtls ? dtls->GetIceTransport() : nullptr;
      if (ice && std::ranges::find(iceTransports, ice) == iceTransports.end()) {
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
    for (const auto &transport : dtlsTransports(pc)) {
      const bool existed = RTCDtlsTransport::holder().Find(transport.get()) != nullptr;
      auto wrapper = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);
      if (!existed) {
        // Python doesn't have the transports yet, their events wait for it
        wrapper->Hold();
        wrapper->GetIceTransport()->Hold();
      }
      Adopt(wrapper);
      if (std::ranges::find(wrappers, wrapper) == wrappers.end()) {
        if (!existed) {
          created.push_back(wrapper->GetIceTransport());
        }
        wrappers.push_back(std::move(wrapper));
      }
    }
    // unused since the last stable state
    std::vector<std::weak_ptr<RTCDtlsTransport>> dropped;
    if (pc->signaling_state() == SignalingState::kStable) {
      for (const auto &transport : _negotiatedTransports) {
        auto wrapper = transport.lock();
        if (wrapper && std::ranges::find(wrappers, wrapper) == wrappers.end()) {
          dropped.emplace_back(wrapper);
        }
      }
      _negotiatedTransports.assign(wrappers.begin(), wrappers.end());
    }
    {
      const TrackedLock lock(_wrappersMutex);
      std::swap(_dtlsTransports, wrappers);
    }
    _factory->workerThread()->PostTask([weak = weak_from_this(), dropped = std::move(dropped)]() {
      for (const auto &transport : dropped) {
        // otherwise closing DTLS closes ICE
        auto dtls = transport.lock();
        if (dtls && dtls->GetCurrentState() == webrtc::DtlsTransportState::kClosed) {
          dtls->GetIceTransport()->OnDropped();
        }
      }
      auto self = weak.lock();
      if (self) {
        self->EmitIceConnectionState();
      }
      ReleaseElsewhere(std::move(self));
    });
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
    BlockingCallOn(_factory->signalingThread(), [&]() {
      transports = dtlsTransports(pc);
      sctpTransport = pc->GetSctpTransport();
    });

    if (auto sctp = sctpTransport ? RTCSctpTransport::holder().Find(sctpTransport.get()) : nullptr) {
      sctp->OnPeerConnectionClosed();
    }
    for (const auto &transport : transports) {
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
      for (const auto &iceTransport : IceTransports()) {
        iceTransport->SetRoleKnown();
      }
    }
  }

  void RTCPeerConnection::RecordRemoteCandidate(const IceCandidateInit &candidate) {
    auto mid = candidate.sdpMid;
    auto pc = connection();
    if (mid.empty() && pc) {
      // signaled by the index of its media section
      BlockingCallOn(_factory->signalingThread(), [&]() {
        const auto *description = pc->remote_description();
        const auto &contents =
            description ? description->description()->contents() : std::vector<webrtc::ContentInfo>();
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
    const auto *description = pc ? pc->remote_description() : nullptr;
    if (description == nullptr) {
      return;
    }
    const auto &contents = description->description()->contents();
    for (size_t index = 0; index < contents.size(); ++index) {
      auto iceTransport = IceTransportByMid(contents[index].mid());
      const auto *candidates = description->candidates(index);
      if (!iceTransport || (candidates == nullptr)) {
        continue;
      }
      for (const auto &candidate : candidates->candidates()) {
        iceTransport->AddRemoteCandidate(IceCandidateInit(*candidate));
      }
    }
  }

  std::optional<std::pair<std::string, std::string>>
  RTCPeerConnection::IceParameters(const webrtc::IceTransportInterface *iceTransport, bool local) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return BlockingCallOn(_factory->signalingThread(), [&]() -> std::optional<std::pair<std::string, std::string>> {
      const auto *description = local ? pc->local_description() : pc->remote_description();
      if (!description) {
        return std::nullopt;
      }
      for (const auto &content : description->description()->contents()) {
        auto dtls = pc->LookupDtlsTransportByMid(content.mid());
        const auto *info = description->description()->GetTransportInfoByName(content.mid());
        if (dtls && dtls->ice_transport().get() == iceTransport && info) {
          return std::make_pair(info->description.ice_ufrag, info->description.ice_pwd);
        }
      }
      return std::nullopt;
    });
  }

  void RTCPeerConnection::OnIceSelectedCandidatePairChanged(const webrtc::CandidatePairChangeEvent & /*unused*/) {
    // the event doesn't tell which transport changed, the ICE transports that Python has check themselves
    for (const auto &ice : IceTransports()) {
      ice->CheckSelectedCandidatePair();
    }
  }

  void RTCPeerConnection::AddIceCandidate(std::function<void()> &onSuccess,
                                          std::function<void(RTCCallbackException)> &onFailure,
                                          const std::string &candidate, const std::optional<std::string> &sdpMid,
                                          std::optional<int> sdpMLineIndex,
                                          const std::optional<std::string> &usernameFragment) {
    auto pc = connection();
    if (!pc) {
      onFailure(RTCCallbackException(closedError("addIceCandidate")));
      return;
    }

    std::optional<RTCCallbackException> error;
    std::set<std::string> mids;
    const webrtc::SessionDescriptionInterface *remote = nullptr;
    BlockingCallOn(_factory->signalingThread(), [&]() {
      remote = pc->remote_description();
      error = candidateSections(remote, sdpMid, sdpMLineIndex, usernameFragment, mids);
    });
    if (error) {
      onFailure(*error);
      return;
    }

    if (candidate.empty()) {
      // the end of candidates, which libwebrtc doesn't take: the remote description shows it
      {
        const std::scoped_lock lock(_remoteEndOfCandidatesMutex);
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
    auto iceCandidate =
        webrtc::IceCandidate::Create(sdpMid.value_or(""), sdpMLineIndex.value_or(0), candidate, &parseError);
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

} // namespace python_webrtc
