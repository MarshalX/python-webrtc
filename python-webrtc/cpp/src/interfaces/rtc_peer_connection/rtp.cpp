//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_peer_connection.h"

#include <algorithm>
#include <map>
#include <set>
#include <type_traits>

#include <absl/strings/match.h>
#include <media/base/media_constants.h>
#include <pc/session_description.h>

#include "../peer_connection_factory.h"
#include "stats_collector_callback.h"

namespace python_webrtc {

  namespace {

    template <typename T>
    webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>
    transceiverOf(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                  const webrtc::scoped_refptr<T> &endpoint) {
      for (const auto &transceiver : pc->GetTransceivers()) {
        if constexpr (std::is_same_v<T, webrtc::RtpSenderInterface>) {
          if (transceiver->sender() == endpoint) {
            return transceiver;
          }
        } else if (transceiver->receiver() == endpoint) {
          return transceiver;
        }
      }
      return nullptr;
    }

    // The media section a transceiver negotiated, in the current remote (for the sender) or local (for the receiver)
    // description; null until it's negotiated, and when it's rejected. On the signaling thread.
    const webrtc::MediaContentDescription *
    negotiatedContent(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc,
                      const webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> &transceiver, bool remote) {
      auto mid = transceiver ? transceiver->mid() : std::nullopt;
      const auto *description = remote ? pc->current_remote_description() : pc->current_local_description();
      const auto *content =
          mid && (description != nullptr) ? description->description()->GetContentByName(*mid) : nullptr;
      return (content != nullptr) && !content->rejected ? content->media_description() : nullptr;
    }

    std::map<std::string, std::string>
    remoteTrackIds(const webrtc::scoped_refptr<webrtc::PeerConnectionInterface> &pc) {
      std::map<std::string, std::string> ids;
      for (const auto &transceiver : pc->GetTransceivers()) {
        if (auto mid = transceiver->mid()) {
          ids.emplace(std::move(*mid), transceiver->receiver()->track()->id());
        }
      }
      return ids;
    }

    bool isSupported(const webrtc::Codec &codec, const webrtc::RtpCapabilities &capabilities, webrtc::MediaType kind) {
      return std::ranges::any_of(capabilities.codecs, [&](const auto &capability) {
        return absl::EqualsIgnoreCase(capability.name, codec.name) && capability.clock_rate == codec.clockrate &&
               (kind != webrtc::MediaType::AUDIO ||
                static_cast<size_t>(capability.num_channels.value_or(1)) == codec.channels);
      });
    }

    // the codecs of a media section this side can use (the remote peer may list unknown ones)
    std::vector<webrtc::RtpCodecParameters> supportedCodecs(const webrtc::MediaContentDescription &content,
                                                            const webrtc::RtpCapabilities &capabilities) {
      std::set<int> kept;
      for (const auto &codec : content.codecs()) {
        if (codec.GetResiliencyType() != webrtc::Codec::ResiliencyType::kRtx &&
            isSupported(codec, capabilities, content.type())) {
          kept.insert(codec.id);
        }
      }
      std::vector<webrtc::RtpCodecParameters> codecs;
      for (const auto &codec : content.codecs()) {
        // a retransmission codec goes with the codec it retransmits
        int associated = 0;
        const bool rtx = codec.GetResiliencyType() == webrtc::Codec::ResiliencyType::kRtx;
        const auto *associatedParam = static_cast<const char *>(webrtc::kCodecParamAssociatedPayloadType);
        if (rtx ? codec.GetParam(associatedParam, &associated) && kept.contains(associated) : kept.contains(codec.id)) {
          codecs.push_back(codec.ToCodecParameters());
        }
      }
      return codecs;
    }

  } // namespace

  webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>
  RTCPeerConnection::TransceiverOf(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender) {
    auto pc = connection();
    return pc ? transceiverOf(pc, sender) : nullptr;
  }

  template <typename T>
  std::vector<webrtc::RtpCodecParameters>
  RTCPeerConnection::NegotiatedCodecsOf(const webrtc::scoped_refptr<T> &endpoint) {
    constexpr bool sending = std::is_same_v<T, webrtc::RtpSenderInterface>;
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return BlockingCallOn(_factory->signalingThread(), [&]() {
      const auto *content = negotiatedContent(pc, transceiverOf(pc, endpoint), sending);
      if (content == nullptr) {
        return std::vector<webrtc::RtpCodecParameters>();
      }
      auto factory = _factory->factory();
      return supportedCodecs(*content, sending ? factory->GetRtpSenderCapabilities(content->type())
                                               : factory->GetRtpReceiverCapabilities(content->type()));
    });
  }

  std::vector<webrtc::RtpCodecParameters>
  RTCPeerConnection::NegotiatedCodecs(const webrtc::scoped_refptr<webrtc::RtpSenderInterface> &sender) {
    return NegotiatedCodecsOf(sender);
  }

  std::vector<webrtc::RtpCodecParameters>
  RTCPeerConnection::NegotiatedCodecs(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver) {
    return NegotiatedCodecsOf(receiver);
  }

  std::vector<webrtc::RtpExtension>
  RTCPeerConnection::NegotiatedHeaderExtensions(const webrtc::scoped_refptr<webrtc::RtpReceiverInterface> &receiver) {
    auto pc = connection();
    if (!pc) {
      return {};
    }
    return BlockingCallOn(_factory->signalingThread(), [&]() {
      const auto *content = negotiatedContent(pc, transceiverOf(pc, receiver), false);
      return content ? content->rtp_header_extensions() : std::vector<webrtc::RtpExtension>();
    });
  }

  webrtc::scoped_refptr<webrtc::PeerConnectionInterface>
  RTCPeerConnection::StatsConnection(const std::function<void(RTCCallbackException)> &onFailure) {
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
      pc->GetStats(webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess, remoteTrackIds(pc)).get());
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
    if (auto pc = StatsConnection(onFailure)) {
      pc->GetStats(receiver, webrtc::make_ref_counted<StatsCollectorCallback>(onSuccess, remoteTrackIds(pc)));
    }
  }

} // namespace python_webrtc
