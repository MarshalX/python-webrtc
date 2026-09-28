//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_candidate.h"

#include <pybind11/stl.h>

namespace python_webrtc {

  static std::optional<std::string> Optional(const std::string &value) {
    return value.empty() ? std::nullopt : std::optional<std::string>(value);
  }

  IceCandidateInit::IceCandidateInit(const webrtc::IceCandidate &iceCandidate)
      : candidate(iceCandidate.ToString()),
        sdpMid(iceCandidate.sdp_mid()),
        sdpMLineIndex(iceCandidate.sdp_mline_index()),
        usernameFragment(Optional(iceCandidate.candidate().username())),
        url(Optional(iceCandidate.server_url())),
        relayProtocol(Optional(iceCandidate.candidate().relay_protocol())) {}

  IceCandidateInit::IceCandidateInit(
      std::string sdpMid, int sdpMLineIndex, std::optional<std::string> usernameFragment)
      : sdpMid(std::move(sdpMid)), sdpMLineIndex(sdpMLineIndex), usernameFragment(std::move(usernameFragment)) {}

  void RTCIceCandidate::Init(pybind11::module &m) {
    pybind11::class_<IceCandidateInit>(m, "IceCandidateInit")
        .def("kwargs", [](const IceCandidateInit &init) {
          pybind11::dict kwargs;
          kwargs["candidate"] = init.candidate;
          kwargs["sdp_mid"] = init.sdpMid;
          kwargs["sdp_m_line_index"] = init.sdpMLineIndex;
          kwargs["username_fragment"] = init.usernameFragment;
          kwargs["url"] = init.url;
          kwargs["relay_protocol"] = init.relayProtocol;
          return kwargs;
        });
  }

} // namespace python_webrtc
