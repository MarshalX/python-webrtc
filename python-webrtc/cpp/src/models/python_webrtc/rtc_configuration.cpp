//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_configuration.h"

#include <pybind11/stl.h>

namespace python_webrtc {

  webrtc::PeerConnectionInterface::IceServers toIceServers(const std::vector<IceServerInit> &iceServers) {
    webrtc::PeerConnectionInterface::IceServers servers;
    for (const auto &server : iceServers) {
      webrtc::PeerConnectionInterface::IceServer iceServer;
      iceServer.urls = server.urls;
      iceServer.username = server.username.value_or("");
      iceServer.password = server.credential.value_or("");
      servers.push_back(std::move(iceServer));
    }
    return servers;
  }

  webrtc::PeerConnectionInterface::RTCConfiguration
  ConfigurationInit::Apply(webrtc::PeerConnectionInterface::RTCConfiguration configuration) const {
    configuration.servers = toIceServers(iceServers);
    configuration.type = iceTransportPolicy;
    configuration.bundle_policy = bundlePolicy;
    configuration.rtcp_mux_policy = rtcpMuxPolicy;
    configuration.ice_candidate_pool_size = iceCandidatePoolSize;
    configuration.always_negotiate_data_channels = alwaysNegotiateDataChannels;
    configuration.crypto_options.srtp.cryptex_policy = rtpHeaderEncryptionPolicy;
    if (certificates) {
      configuration.certificates.clear();
      for (const auto &certificate : *certificates) {
        configuration.certificates.push_back(certificate->certificate());
      }
    }
    if (portRange) {
      configuration.set_min_port(portRange->first);
      configuration.set_max_port(portRange->second);
    }
    return configuration;
  }

  void ConfigurationInit::Init(pybind11::module &m) {
    pybind11::class_<IceServerInit>(m, "IceServerInit")
        .def(pybind11::init<>())
        .def_readwrite("urls", &IceServerInit::urls)
        .def_readwrite("username", &IceServerInit::username)
        .def_readwrite("credential", &IceServerInit::credential);

    pybind11::class_<ConfigurationInit>(m, "ConfigurationInit")
        .def(pybind11::init<>())
        .def_readwrite("iceServers", &ConfigurationInit::iceServers)
        .def_readwrite("iceTransportPolicy", &ConfigurationInit::iceTransportPolicy)
        .def_readwrite("bundlePolicy", &ConfigurationInit::bundlePolicy)
        .def_readwrite("rtcpMuxPolicy", &ConfigurationInit::rtcpMuxPolicy)
        .def_readwrite("iceCandidatePoolSize", &ConfigurationInit::iceCandidatePoolSize)
        .def_readwrite("portRange", &ConfigurationInit::portRange)
        .def_readwrite("alwaysNegotiateDataChannels", &ConfigurationInit::alwaysNegotiateDataChannels)
        .def_readwrite("rtpHeaderEncryptionPolicy", &ConfigurationInit::rtpHeaderEncryptionPolicy)
        .def_readwrite("certificates", &ConfigurationInit::certificates);
  }

} // namespace python_webrtc
