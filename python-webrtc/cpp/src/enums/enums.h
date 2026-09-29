//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_ENUMS_ENUMS_H_
#define PYTHON_WEBRTC_ENUMS_ENUMS_H_

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>

#include <api/crypto/crypto_options.h>
#include <api/data_channel_interface.h>
#include <api/dtls_transport_interface.h>
#include <api/jsep.h>
#include <api/media_stream_interface.h>
#include <api/media_types.h>
#include <api/peer_connection_interface.h>
#include <api/priority.h>
#include <api/rtc_error.h>
#include <api/rtp_parameters.h>
#include <api/rtp_transceiver_direction.h>
#include <api/sctp_transport_interface.h>
#include <api/transport/enums.h>
#include <p2p/base/ice_transport_internal.h>
#include <p2p/base/transport_description.h>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  enum class RTCIceComponent : uint8_t { kRtp, kRtcp };

  // the media type of a kind of track ("audio" or "video")
  std::optional<webrtc::MediaType> mediaTypeOf(const std::string &kind);

  // A C++ enum that Python sees as the str enum `name` of webrtc.enums, converted by the values listed here.
  // Every file that binds one must include this header, or pybind11 silently uses its own caster.
  template <typename T>
  struct StrEnum {};

  template <typename T, typename = void>
  struct IsStrEnum : std::false_type {};
  template <typename T>
  struct IsStrEnum<T, std::void_t<decltype(StrEnum<T>::values)>> : std::true_type {};

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::PeerConnectionState> {
    using State = webrtc::PeerConnectionInterface::PeerConnectionState;
    static constexpr auto name = pybind11::detail::const_name("RTCPeerConnectionState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kNew, "new"},
        {State::kConnecting, "connecting"},
        {State::kConnected, "connected"},
        {State::kDisconnected, "disconnected"},
        {State::kFailed, "failed"},
        {State::kClosed, "closed"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::SignalingState> {
    using State = webrtc::PeerConnectionInterface::SignalingState;
    static constexpr auto name = pybind11::detail::const_name("RTCSignalingState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kStable, "stable"},
        {State::kHaveLocalOffer, "have-local-offer"},
        {State::kHaveLocalPrAnswer, "have-local-pranswer"},
        {State::kHaveRemoteOffer, "have-remote-offer"},
        {State::kHaveRemotePrAnswer, "have-remote-pranswer"},
        {State::kClosed, "closed"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::IceConnectionState> {
    using State = webrtc::PeerConnectionInterface::IceConnectionState;
    static constexpr auto name = pybind11::detail::const_name("RTCIceConnectionState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kIceConnectionNew, "new"},
        {State::kIceConnectionChecking, "checking"},
        {State::kIceConnectionConnected, "connected"},
        {State::kIceConnectionCompleted, "completed"},
        {State::kIceConnectionFailed, "failed"},
        {State::kIceConnectionDisconnected, "disconnected"},
        {State::kIceConnectionClosed, "closed"},
        {State::kIceConnectionMax, "max"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::IceGatheringState> {
    using State = webrtc::PeerConnectionInterface::IceGatheringState;
    static constexpr auto name = pybind11::detail::const_name("RTCIceGatheringState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kIceGatheringNew, "new"},
        {State::kIceGatheringGathering, "gathering"},
        {State::kIceGatheringComplete, "complete"},
    });
  };

  template <>
  struct StrEnum<webrtc::SdpType> {
    static constexpr auto name = pybind11::detail::const_name("RTCSdpType");
    static constexpr auto values = std::to_array<std::pair<webrtc::SdpType, const char *>>({
        {webrtc::SdpType::kOffer, "offer"},
        {webrtc::SdpType::kPrAnswer, "pranswer"},
        {webrtc::SdpType::kAnswer, "answer"},
        {webrtc::SdpType::kRollback, "rollback"},
    });
  };

  template <>
  struct StrEnum<webrtc::MediaStreamTrackInterface::TrackState> {
    using State = webrtc::MediaStreamTrackInterface::TrackState;
    static constexpr auto name = pybind11::detail::const_name("MediaStreamTrackState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kLive, "live"},
        {State::kEnded, "ended"},
    });
  };

  template <>
  struct StrEnum<webrtc::RtpTransceiverDirection> {
    using Direction = webrtc::RtpTransceiverDirection;
    static constexpr auto name = pybind11::detail::const_name("TransceiverDirection");
    static constexpr auto values = std::to_array<std::pair<Direction, const char *>>({
        {Direction::kSendRecv, "sendrecv"},
        {Direction::kSendOnly, "sendonly"},
        {Direction::kRecvOnly, "recvonly"},
        {Direction::kInactive, "inactive"},
        {Direction::kStopped, "stopped"},
    });
  };

  template <>
  struct StrEnum<webrtc::MediaType> {
    static constexpr auto name = pybind11::detail::const_name("MediaType");
    static constexpr auto values = std::to_array<std::pair<webrtc::MediaType, const char *>>({
        {webrtc::MediaType::AUDIO, "audio"},
        {webrtc::MediaType::VIDEO, "video"},
        {webrtc::MediaType::DATA, "data"},
        {webrtc::MediaType::UNSUPPORTED, "unsupported"},
    });
  };

  template <>
  struct StrEnum<RTCIceComponent> {
    static constexpr auto name = pybind11::detail::const_name("RTCIceComponent");
    static constexpr auto values = std::to_array<std::pair<RTCIceComponent, const char *>>({
        {RTCIceComponent::kRtp, "rtp"},
        {RTCIceComponent::kRtcp, "rtcp"},
    });
  };

  template <>
  struct StrEnum<webrtc::IceRole> {
    static constexpr auto name = pybind11::detail::const_name("RTCIceRole");
    static constexpr auto values = std::to_array<std::pair<webrtc::IceRole, const char *>>({
        {webrtc::IceRole::ICEROLE_CONTROLLING, "controlling"},
        {webrtc::IceRole::ICEROLE_CONTROLLED, "controlled"},
        {webrtc::IceRole::ICEROLE_UNKNOWN, "unknown"},
    });
  };

  template <>
  struct StrEnum<webrtc::IceTransportState> {
    using State = webrtc::IceTransportState;
    static constexpr auto name = pybind11::detail::const_name("RTCIceTransportState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kNew, "new"},
        {State::kChecking, "checking"},
        {State::kConnected, "connected"},
        {State::kCompleted, "completed"},
        {State::kDisconnected, "disconnected"},
        {State::kFailed, "failed"},
        {State::kClosed, "closed"},
    });
  };

  template <>
  struct StrEnum<webrtc::IceGatheringState> {
    static constexpr auto name = pybind11::detail::const_name("CricketIceGatheringState");
    static constexpr auto values = std::to_array<std::pair<webrtc::IceGatheringState, const char *>>({
        {webrtc::IceGatheringState::kIceGatheringNew, "new"},
        {webrtc::IceGatheringState::kIceGatheringGathering, "gathering"},
        {webrtc::IceGatheringState::kIceGatheringComplete, "complete"},
    });
  };

  template <>
  struct StrEnum<webrtc::DtlsTransportState> {
    using State = webrtc::DtlsTransportState;
    static constexpr auto name = pybind11::detail::const_name("DtlsTransportState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kNew, "new"},
        {State::kConnecting, "connecting"},
        {State::kConnected, "connected"},
        {State::kClosed, "closed"},
        {State::kFailed, "failed"},
    });
  };

  template <>
  struct StrEnum<webrtc::SctpTransportState> {
    using State = webrtc::SctpTransportState;
    static constexpr auto name = pybind11::detail::const_name("SctpTransportState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kNew, "new"},
        {State::kConnecting, "connecting"},
        {State::kConnected, "connected"},
        {State::kClosed, "closed"},
    });
  };

  template <>
  struct StrEnum<webrtc::DataChannelInterface::DataState> {
    using State = webrtc::DataChannelInterface::DataState;
    static constexpr auto name = pybind11::detail::const_name("RTCDataChannelState");
    static constexpr auto values = std::to_array<std::pair<State, const char *>>({
        {State::kConnecting, "connecting"},
        {State::kOpen, "open"},
        {State::kClosing, "closing"},
        {State::kClosed, "closed"},
    });
  };

  template <>
  struct StrEnum<webrtc::Priority> {
    static constexpr auto name = pybind11::detail::const_name("RTCPriorityType");
    static constexpr auto values = std::to_array<std::pair<webrtc::Priority, const char *>>({
        {webrtc::Priority::kVeryLow, "very-low"},
        {webrtc::Priority::kLow, "low"},
        {webrtc::Priority::kMedium, "medium"},
        {webrtc::Priority::kHigh, "high"},
    });
  };

  template <>
  struct StrEnum<webrtc::DegradationPreference> {
    using Preference = webrtc::DegradationPreference;
    static constexpr auto name = pybind11::detail::const_name("RTCDegradationPreference");
    static constexpr auto values = std::to_array<std::pair<Preference, const char *>>({
        {Preference::MAINTAIN_FRAMERATE, "maintain-framerate"},
        {Preference::MAINTAIN_RESOLUTION, "maintain-resolution"},
        {Preference::BALANCED, "balanced"},
        {Preference::MAINTAIN_FRAMERATE_AND_RESOLUTION, "maintain-framerate-and-resolution"},
    });
  };

  // NONE is None in Python
  template <>
  struct StrEnum<webrtc::RTCErrorDetailType> {
    using Detail = webrtc::RTCErrorDetailType;
    static constexpr auto name = pybind11::detail::const_name("RTCErrorDetailType");
    static constexpr auto values = std::to_array<std::pair<Detail, const char *>>({
        {Detail::DATA_CHANNEL_FAILURE, "data-channel-failure"},
        {Detail::DTLS_FAILURE, "dtls-failure"},
        {Detail::FINGERPRINT_FAILURE, "fingerprint-failure"},
        {Detail::SCTP_FAILURE, "sctp-failure"},
        {Detail::SDP_SYNTAX_ERROR, "sdp-syntax-error"},
        {Detail::HARDWARE_ENCODER_NOT_AVAILABLE, "hardware-encoder-not-available"},
        {Detail::HARDWARE_ENCODER_ERROR, "hardware-encoder-error"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::IceTransportsType> {
    using Policy = webrtc::PeerConnectionInterface::IceTransportsType;
    static constexpr auto name = pybind11::detail::const_name("RTCIceTransportPolicy");
    static constexpr auto values = std::to_array<std::pair<Policy, const char *>>({
        {Policy::kAll, "all"},
        {Policy::kRelay, "relay"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::BundlePolicy> {
    using Policy = webrtc::PeerConnectionInterface::BundlePolicy;
    static constexpr auto name = pybind11::detail::const_name("RTCBundlePolicy");
    static constexpr auto values = std::to_array<std::pair<Policy, const char *>>({
        {Policy::kBundlePolicyBalanced, "balanced"},
        {Policy::kBundlePolicyMaxCompat, "max-compat"},
        {Policy::kBundlePolicyMaxBundle, "max-bundle"},
    });
  };

  template <>
  struct StrEnum<webrtc::PeerConnectionInterface::RtcpMuxPolicy> {
    using Policy = webrtc::PeerConnectionInterface::RtcpMuxPolicy;
    static constexpr auto name = pybind11::detail::const_name("RTCRtcpMuxPolicy");
    static constexpr auto values = std::to_array<std::pair<Policy, const char *>>({
        {Policy::kRtcpMuxPolicyRequire, "require"},
    });
  };

  template <>
  struct StrEnum<webrtc::CryptoOptions::Srtp::CryptexPolicy> {
    using Policy = webrtc::CryptoOptions::Srtp::CryptexPolicy;
    static constexpr auto name = pybind11::detail::const_name("RTCRtpHeaderEncryptionPolicy");
    static constexpr auto values = std::to_array<std::pair<Policy, const char *>>({
        {Policy::kNegotiate, "negotiate"},
        {Policy::kRequire, "require"},
    });
  };

} // namespace python_webrtc

namespace pybind11::detail {

  // not the caster of py::enum_ and py::native_enum
  template <typename T>
  struct type_caster_enum_type_enabled<T, enable_if_t<python_webrtc::IsStrEnum<T>::value>> : std::false_type {};

  template <typename T>
  class type_caster<T, enable_if_t<python_webrtc::IsStrEnum<T>::value>> {
    using Enum = python_webrtc::StrEnum<T>;

  public:
    PYBIND11_TYPE_CASTER(T, const_name("webrtc.enums.") + Enum::name);

    // a member of the Python enum, or its value: like a wrong type, another string is a TypeError (as it is for
    // a WebIDL enum)
    bool load(handle src, bool /*unused*/) {
      if (!isinstance<str>(src)) {
        return false;
      }
      auto text = src.cast<std::string>();
      for (const auto &[member, memberValue] : Enum::values) {
        if (text == memberValue) {
          value = member;
          return true;
        }
      }
      return false;
    }

    static handle cast(T src, return_value_policy /*unused*/, handle /*unused*/) {
      for (const auto &[member, memberValue] : Enum::values) {
        if (member == src) {
          // looked up when converting, as webrtc.enums may be imported after this module
          return module_::import("webrtc.enums").attr(Enum::name.text)(memberValue).release();
        }
      }
      throw value_error(std::string(Enum::name.text) + " has no member for " + std::to_string(static_cast<int>(src)));
    }
  };

} // namespace pybind11::detail

#endif // PYTHON_WEBRTC_ENUMS_ENUMS_H_
