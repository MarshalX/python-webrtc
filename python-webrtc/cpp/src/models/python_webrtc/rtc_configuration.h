//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>

#include <api/peer_connection_interface.h>

#include "rtc_certificate.h"

namespace python_webrtc {

  struct IceServerInit {
    std::vector<std::string> urls;
    std::optional<std::string> username;
    std::optional<std::string> credential;
  };

  // The configuration of a connection as it was set, which is what getConfiguration() returns.
  // webrtc.RTCConfiguration validates it before it gets here.
  struct ConfigurationInit {
    std::vector<IceServerInit> iceServers;
    webrtc::PeerConnectionInterface::IceTransportsType iceTransportPolicy =
        webrtc::PeerConnectionInterface::IceTransportsType::kAll;
    webrtc::PeerConnectionInterface::BundlePolicy bundlePolicy =
        webrtc::PeerConnectionInterface::BundlePolicy::kBundlePolicyBalanced;
    webrtc::PeerConnectionInterface::RtcpMuxPolicy rtcpMuxPolicy =
        webrtc::PeerConnectionInterface::RtcpMuxPolicy::kRtcpMuxPolicyRequire;
    int iceCandidatePoolSize = 0;
    std::optional<std::pair<int, int>> portRange;
    bool alwaysNegotiateDataChannels = false;
    // cryptex (RFC 9335), offered by default
    webrtc::CryptoOptions::Srtp::CryptexPolicy rtpHeaderEncryptionPolicy =
        webrtc::CryptoOptions::Srtp::CryptexPolicy::kNegotiate;
    // when unset, the connection keeps the certificates it has
    std::optional<std::vector<std::shared_ptr<Certificate>>> certificates;

    // the libwebrtc configuration, on top of the one the connection has (for its settings that can't change)
    [[nodiscard]] webrtc::PeerConnectionInterface::RTCConfiguration Apply(
        webrtc::PeerConnectionInterface::RTCConfiguration configuration) const;

    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc
