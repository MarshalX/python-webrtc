//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_ICE_CANDIDATE_H_
#define PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_ICE_CANDIDATE_H_

#include <optional>
#include <string>

#include <pybind11/pybind11.h>

#include <api/jsep.h>

namespace python_webrtc {

  // The keyword arguments of webrtc.RTCIceCandidate for a candidate of libwebrtc
  struct IceCandidateInit {
    explicit IceCandidateInit(const webrtc::IceCandidate &candidate);

    // the end of candidates of a media section
    IceCandidateInit(std::string sdpMid, int sdpMLineIndex, std::optional<std::string> usernameFragment);

    std::string candidate;
    std::string sdpMid;
    int sdpMLineIndex;
    std::optional<std::string> usernameFragment;
    std::optional<std::string> url;
    std::optional<std::string> relayProtocol;
  };

  class RTCIceCandidate {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_ICE_CANDIDATE_H_
