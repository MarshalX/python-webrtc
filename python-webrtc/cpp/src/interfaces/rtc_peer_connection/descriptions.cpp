//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"

#include <algorithm>
#include <utility>

#include "../peer_connection_factory.h"
#include "create_session_description_observer.h"
#include "sdp.h"
#include "set_session_description_observer.h"

namespace python_webrtc {

  // the snapshots Python didn't apply (like while it has no loop) aren't going to be
  static constexpr size_t kMaxPendingSnapshots = 32;

  class RTCPeerConnection::HeldOperationEvents {
  public:
    HeldOperationEvents(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                        std::vector<std::shared_ptr<RTCIceTransport>> iceTransports,
                        const std::shared_ptr<RTCPeerConnection> &connection, bool holdGathering)
        : _connection(connection), _gatheringHeld(holdGathering) {
      connection->_heldTransportStates.Hold();
      if (holdGathering) {
        connection->_heldGathering.Hold();
      }
      for (auto &iceTransport : iceTransports) {
        if (!iceTransport->IsHeld()) {
          iceTransport->Hold();
          _iceTransports.push_back(std::move(iceTransport));
        }
      }
      for (const auto &transceiver : pc->GetTransceivers()) {
        auto track = MediaStreamTrack::registry().Find(transceiver->receiver()->track().get());
        if (track) {
          track->HoldEnded();
          _tracks.emplace_back(std::move(track));
        }
      }
    }

    // also when the operation fails before it starts
    ~HeldOperationEvents() { Release(); }

    HeldOperationEvents(const HeldOperationEvents &) = delete;
    HeldOperationEvents &operator=(const HeldOperationEvents &) = delete;

    void Release() {
      const std::scoped_lock lock(_mutex);
      for (const auto &track : _tracks) {
        track->ReleaseEnded();
      }
      _tracks.clear();
      for (const auto &iceTransport : _iceTransports) {
        iceTransport->Release();
      }
      _iceTransports.clear();
      if (auto connection = _connection.lock()) {
        connection->_heldTransportStates.Release();
        if (_gatheringHeld) {
          connection->_heldGathering.Release();
        }
      }
      _connection.reset();
    }

  private:
    std::mutex _mutex;
    std::vector<std::shared_ptr<MediaStreamTrack>> _tracks;
    std::vector<std::shared_ptr<RTCIceTransport>> _iceTransports;
    // whose transport states and local gathering are held
    std::weak_ptr<RTCPeerConnection> _connection;
    bool _gatheringHeld;
  };

  namespace {

    bool canSetLocal(webrtc::SdpType type, RTCPeerConnection::SignalingState state) {
      using SignalingState = RTCPeerConnection::SignalingState;
      if (type == webrtc::SdpType::kOffer) {
        return state == SignalingState::kStable || state == SignalingState::kHaveLocalOffer;
      }
      if (type == webrtc::SdpType::kRollback) {
        return state == SignalingState::kHaveLocalOffer || state == SignalingState::kHaveLocalPrAnswer;
      }
      return state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
    }

    std::vector<const webrtc::SessionDescriptionInterface *>
    liveDescriptions(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
      return {pc->current_local_description(), pc->current_remote_description(), pc->pending_local_description(),
              pc->pending_remote_description()};
    }

  } // namespace

  void RTCPeerConnection::CreateOffer(std::shared_ptr<Mailbox> mailbox, uint64_t token, bool iceRestart) {
    Completion completion(std::move(mailbox), token);
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      completion.Fail(RTCCallbackException(closedError("createOffer")));
      return;
    }
    if (state != SignalingState::kStable && state != SignalingState::kHaveLocalOffer) {
      completion.Fail(
          RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
                               "Failed to execute 'createOffer' on 'RTCPeerConnection': Called in wrong state: " +
                                   std::string(webrtc::PeerConnectionInterface::AsString(state))));
      return;
    }

    auto observer = webrtc::make_ref_counted<CreateSessionDescriptionObserver>(
        weak_from_this(), std::make_shared<Completion>(std::move(completion)));

    auto options = webrtc::PeerConnectionInterface::RTCOfferAnswerOptions();
    options.ice_restart = iceRestart;

    pc->CreateOffer(observer.get(), options);
  }

  void RTCPeerConnection::CreateAnswer(std::shared_ptr<Mailbox> mailbox, uint64_t token) {
    Completion completion(std::move(mailbox), token);
    auto pc = connection();
    if (!pc || pc->signaling_state() == SignalingState::kClosed) {
      completion.Fail(RTCCallbackException(closedError("createAnswer")));
      return;
    }

    auto observer = webrtc::make_ref_counted<CreateSessionDescriptionObserver>(
        weak_from_this(), std::make_shared<Completion>(std::move(completion)));
    pc->CreateAnswer(observer.get(), webrtc::PeerConnectionInterface::RTCOfferAnswerOptions());
  }

  void RTCPeerConnection::SaveCreatedDescription(const RTCSessionDescriptionInit &description) {
    const std::scoped_lock lock(_createdMutex);
    (description.type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer) = description.sdp;
  }

  std::function<void(webrtc::RTCError)>
  RTCPeerConnection::DescriptionCompletion(std::shared_ptr<Completion> completion,
                                           const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                                           DescriptionKind kind) {
    const bool remote = kind == DescriptionKind::kRemote;
    // a local description starts gathering, the candidates come after it
    auto held = std::make_shared<HeldOperationEvents>(pc, IceTransports(), shared_from_this(), !remote);
    if (remote) {
      SnapshotRemoteStreams(pc);
    }
    return [weak = weak_from_this(), completion = std::move(completion), held, remote](webrtc::RTCError error) {
      auto self = weak.lock();
      if (!self || self->IsClosed()) {
        completion->Fail(RTCCallbackException(closedError(remote ? "setRemoteDescription" : "setLocalDescription")));
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
        completion->Succeed();
        // their gathering events come after the operation
        for (const auto &iceTransport : created) {
          iceTransport->CreatedByDescription();
        }
      } else {
        completion->Fail(RTCCallbackException(std::move(error)));
      }
      held->Release();
    };
  }

  void RTCPeerConnection::SetLocalDescription(std::shared_ptr<Mailbox> mailbox, uint64_t token,
                                              const std::optional<RTCSessionDescriptionInit> &init) {
    Completion completion(std::move(mailbox), token);
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      completion.Fail(RTCCallbackException(closedError("setLocalDescription")));
      return;
    }
    if (init && !canSetLocal(init->type, state)) {
      completion.Fail(RTCCallbackException(
          webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The description type doesn't match "
          "the signaling state."));
      return;
    }

    if (!init || (init->sdp.empty() && init->type != webrtc::SdpType::kRollback)) {
      // without a type, an answer in the states that wait for one, an offer otherwise
      const bool waitsForAnswer =
          state == SignalingState::kHaveRemoteOffer || state == SignalingState::kHaveLocalPrAnswer;
      const auto implicitType = waitsForAnswer ? webrtc::SdpType::kAnswer : webrtc::SdpType::kOffer;
      auto type = init ? init->type : implicitType;
      auto shared = std::make_shared<Completion>(std::move(completion));
      auto complete = DescriptionCompletion(shared, pc, DescriptionKind::kLocal);
      if (type == webrtc::SdpType::kOffer ||
          (type == webrtc::SdpType::kAnswer && state == SignalingState::kHaveRemoteOffer)) {
        // libwebrtc creates the offer or the answer the signaling state calls for
        pc->SetLocalDescription(webrtc::make_ref_counted<SetLocalDescriptionObserver>(std::move(complete)));
      } else {
        SetImplicitAnswer(pc, type, std::move(complete), shared);
      }
      return;
    }

    if (init->type != webrtc::SdpType::kRollback) {
      const std::scoped_lock lock(_createdMutex);
      if (fingerprintChanged(init->type == webrtc::SdpType::kOffer ? _lastOffer : _lastAnswer, init->sdp)) {
        completion.Fail(RTCCallbackException(
            webrtc::RTCErrorType::INVALID_MODIFICATION,
            "Failed to execute 'setLocalDescription' on 'RTCPeerConnection': The SDP does not match the previously "
            "generated SDP for this type"));
        return;
      }
    }

    std::optional<RTCCallbackException> error;
    auto description = parseDescription(*init, error);
    if (error) {
      completion.Fail(*error);
      return;
    }
    pc->SetLocalDescription(std::move(description),
                            webrtc::make_ref_counted<SetLocalDescriptionObserver>(DescriptionCompletion(
                                std::make_shared<Completion>(std::move(completion)), pc, DescriptionKind::kLocal)));
  }

  void RTCPeerConnection::SetImplicitAnswer(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                                            webrtc::SdpType type, std::function<void(webrtc::RTCError)> complete,
                                            const std::shared_ptr<Completion> &completion) {
    auto observer = webrtc::make_ref_counted<SetLocalDescriptionObserver>(std::move(complete));
    auto apply = [pc, observer, type, completion](const std::string &sdp) {
      std::optional<RTCCallbackException> error;
      auto description = parseDescription(RTCSessionDescriptionInit(type, sdp), error);
      if (error) {
        completion->Fail(*error);
        return;
      }
      pc->SetLocalDescription(std::move(description), observer);
    };
    std::string lastAnswer;
    {
      const std::scoped_lock lock(_createdMutex);
      lastAnswer = _lastAnswer;
    }
    if (!lastAnswer.empty()) {
      apply(lastAnswer);
      return;
    }
    auto answerObserver = webrtc::make_ref_counted<CreateSessionDescriptionObserver>(
        weak_from_this(), completion, [apply](const RTCSessionDescription &answer) { apply(answer.init().sdp); });
    pc->CreateAnswer(answerObserver.get(), webrtc::PeerConnectionInterface::RTCOfferAnswerOptions());
  }

  void RTCPeerConnection::SetRemoteDescription(std::shared_ptr<Mailbox> mailbox, uint64_t token,
                                               const RTCSessionDescriptionInit &init) {
    Completion completion(std::move(mailbox), token);
    auto pc = connection();
    auto state = pc ? pc->signaling_state() : SignalingState::kClosed;
    if (state == SignalingState::kClosed) {
      completion.Fail(RTCCallbackException(closedError("setRemoteDescription")));
      return;
    }

    // the state is checked before the SDP is parsed
    const bool answer = init.type == webrtc::SdpType::kAnswer || init.type == webrtc::SdpType::kPrAnswer;
    const bool rollback = init.type == webrtc::SdpType::kRollback;
    if ((answer && state != SignalingState::kHaveLocalOffer && state != SignalingState::kHaveRemotePrAnswer) ||
        (rollback && state != SignalingState::kHaveRemoteOffer && state != SignalingState::kHaveRemotePrAnswer)) {
      completion.Fail(RTCCallbackException(
          webrtc::RTCErrorType::INVALID_STATE,
          "Failed to execute 'setRemoteDescription' on 'RTCPeerConnection': Called in wrong state: " +
              std::string(webrtc::PeerConnectionInterface::AsString(state))));
      return;
    }

    // shared by the rollback and the application of the description
    auto shared = std::make_shared<Completion>(std::move(completion));
    auto complete = std::make_shared<const std::function<void(webrtc::RTCError)>>(
        DescriptionCompletion(shared, pc, DescriptionKind::kRemote));
    auto apply = [init, complete, shared](const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
      std::optional<RTCCallbackException> error;
      auto description = parseDescription(init, error);
      if (error) {
        shared->Fail(*error);
        return;
      }
      removeBlockedCandidates(*description);
      pc->SetRemoteDescription(std::move(description),
                               webrtc::make_ref_counted<SetRemoteDescriptionObserver>(
                                   [complete](webrtc::RTCError error) { (*complete)(std::move(error)); }));
    };

    if (init.type == webrtc::SdpType::kOffer && state == SignalingState::kHaveLocalOffer) {
      // an offer in have-local-offer rolls the local one back first (perfect negotiation),
      // even if the offer turns out to be invalid
      auto rollbackObserver = webrtc::make_ref_counted<SetLocalDescriptionObserver>(
          [weak = weak_from_this(), apply, complete](webrtc::RTCError rollbackError) {
            auto self = weak.lock();
            auto pc = self ? self->connection() : nullptr;
            if (!rollbackError.ok()) {
              (*complete)(std::move(rollbackError));
            } else if (!pc) {
              (*complete)(closedError("setRemoteDescription"));
            } else {
              apply(pc);
            }
          });
      pc->SetLocalDescription(webrtc::CreateSessionDescription(webrtc::SdpType::kRollback, ""), rollbackObserver);
      return;
    }

    apply(pc);
  }

  RTCPeerConnection::DescriptionView
  RTCPeerConnection::ReadDescription(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                                     DescriptionKind kind) {
    DescriptionView view;
    switch (kind) {
    case DescriptionKind::kLocal:
      view.description = pc->local_description();
      break;
    case DescriptionKind::kRemote:
      view.description = pc->remote_description();
      break;
    case DescriptionKind::kCurrentLocal:
      view.description = pc->current_local_description();
      break;
    case DescriptionKind::kCurrentRemote:
      view.description = pc->current_remote_description();
      break;
    case DescriptionKind::kPendingLocal:
      view.description = pc->pending_local_description();
      break;
    case DescriptionKind::kPendingRemote:
      view.description = pc->pending_remote_description();
      break;
    }
    if (view.description == nullptr) {
      return view;
    }
    auto &init = view.init.emplace(RTCSessionDescriptionInit::Wrap(view.description));
    const bool local = kind == DescriptionKind::kLocal || kind == DescriptionKind::kCurrentLocal ||
                       kind == DescriptionKind::kPendingLocal;
    if (local && pc->ice_gathering_state() == IceGatheringState::kIceGatheringComplete) {
      init.sdp = addEndOfCandidates(init.sdp);
    } else if (!local && view.description == pc->remote_description()) {
      // the end of remote candidates, from addIceCandidate
      const std::scoped_lock lock(_remoteEndOfCandidatesMutex);
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
      const std::scoped_lock lock(_descriptionsMutex);
      if (IsBound() && _shown && _shownGeneration == _descriptionsGeneration) {
        view = _shown->kinds[static_cast<size_t>(kind)];
        live = _shown->live;
        shown = true;
      }
    }
    if (!shown) {
      // the description is owned by the peer connection and must be read on the signaling thread
      BlockingCallOn(_factory->signalingThread(), [&]() {
        view = ReadDescription(pc, kind);
        live = liveDescriptions(pc);
      });
    }

    const std::scoped_lock lock(_descriptionsMutex);
    // while events are delivered, a description only changes with them; without events it's always current
    const bool refresh = shown || !IsBound() || _descriptionsCachedGeneration != _descriptionsGeneration;
    _descriptionsCachedGeneration = _descriptionsGeneration;
    return FindOrCreateDescription(view, live, refresh);
  }

  std::shared_ptr<RTCSessionDescription> RTCPeerConnection::FindOrCreateDescription(
      const DescriptionView &view, const std::vector<const webrtc::SessionDescriptionInterface *> &live, bool refresh) {
    // descriptions that aren't set anymore are forgotten, so a new one at the same address is a new object
    std::vector<std::pair<const webrtc::SessionDescriptionInterface *, std::shared_ptr<RTCSessionDescription>>> kept;
    std::shared_ptr<RTCSessionDescription> result;
    for (auto &entry : _descriptions) {
      if (std::ranges::find(live, entry.first) == live.end()) {
        continue;
      }
      const auto &init = entry.second->init();
      if (view.init && entry.first == view.description && init.type == view.init->type &&
          (!refresh || init.sdp == view.init->sdp)) {
        result = entry.second;
      }
      kept.push_back(std::move(entry));
    }
    // set with the description
    if (view.init && !result) {
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
    if (!pc || !IsBound()) {
      return 0;
    }
    DescriptionsSnapshot snapshot;
    for (size_t kind = 0; kind < kDescriptionKinds; ++kind) {
      snapshot.kinds[kind] = ReadDescription(pc, static_cast<DescriptionKind>(kind));
    }
    snapshot.live = liveDescriptions(pc);
    const std::scoped_lock lock(_descriptionsMutex);
    auto id = ++_lastSnapshot;
    _snapshots.emplace(id, std::move(snapshot));
    while (_snapshots.size() > kMaxPendingSnapshots) {
      _snapshots.erase(_snapshots.begin());
    }
    return id;
  }

  void RTCPeerConnection::ApplyDescriptions(std::optional<uint64_t> snapshot) {
    const std::scoped_lock lock(_descriptionsMutex);
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
    const std::scoped_lock lock(_descriptionsMutex);
    ++_descriptionsGeneration;
  }

} // namespace python_webrtc
