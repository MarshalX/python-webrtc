//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_SDP_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_SDP_H_

#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include <api/candidate.h>
#include <api/jsep.h>

#include "../../exceptions.h"
#include "../../models/python_webrtc/rtc_ice_candidate.h"
#include "../../models/python_webrtc/rtc_session_description.h"

namespace python_webrtc {

  // A remote TCP candidate on a port Fetch blocks is ignored, as the WebRTC specification requires
  // (https://fetch.spec.whatwg.org/#bad-port)
  bool isBlockedCandidate(const webrtc::Candidate &candidate);

  void removeBlockedCandidates(webrtc::SessionDescriptionInterface &description);

  std::unique_ptr<webrtc::SessionDescriptionInterface> parseDescription(const RTCSessionDescriptionInit &init,
                                                                        std::optional<RTCCallbackException> &error);

  // End-of-candidates candidates of a local description, one per transport (the first media section of each)
  std::vector<IceCandidateInit> endOfCandidates(const webrtc::SessionDescriptionInterface *description);

  // Adds a=end-of-candidates to the media sections of a description (of these mids, or all of them)
  std::string addEndOfCandidates(const std::string &sdp, const std::set<std::string> *mids = nullptr);

  // The media sections a candidate is for (all of them for a null mid and index), into mids, and whether its ufrag
  // is known. On the signaling thread.
  std::optional<RTCCallbackException> candidateSections(const webrtc::SessionDescriptionInterface *remote,
                                                        const std::optional<std::string> &sdpMid,
                                                        std::optional<int> sdpMLineIndex,
                                                        const std::optional<std::string> &usernameFragment,
                                                        std::set<std::string> &mids);

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_SDP_H_
