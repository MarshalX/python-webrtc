//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "sdp.h"

#include <algorithm>
#include <string_view>
#include <utility>

#include <pc/session_description.h>

namespace python_webrtc {

  namespace {

    // the line of an SDP parse error, counting from 1
    std::optional<int> lineNumber(const std::string &sdp, const std::string &line) {
      auto pos = line.empty() ? std::string::npos : sdp.find(line);
      if (pos == std::string::npos) {
        return std::nullopt;
      }
      return 1 + static_cast<int>(std::count(sdp.begin(), sdp.begin() + static_cast<std::ptrdiff_t>(pos), '\n'));
    }

    constexpr std::string_view kMidPrefix = "a=mid:";

  } // namespace

  bool isBlockedCandidate(const webrtc::Candidate &candidate) {
    static const std::set<int> badPorts = {
        0,    1,    7,    9,    11,   13,   15,   17,   19,   20,   21,   22,   23,   25,   37,   42,   43,
        53,   69,   77,   79,   87,   95,   101,  102,  103,  104,  109,  110,  111,  113,  115,  117,  119,
        123,  135,  137,  139,  143,  161,  179,  389,  427,  465,  512,  513,  514,  515,  526,  530,  531,
        532,  540,  548,  554,  556,  563,  587,  601,  636,  989,  990,  993,  995,  1719, 1720, 1723, 2049,
        3659, 4045, 4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080};
    return candidate.protocol() == "tcp" && badPorts.contains(candidate.address().port());
  }

  void removeBlockedCandidates(webrtc::SessionDescriptionInterface &description) {
    std::vector<std::unique_ptr<webrtc::IceCandidate>> blocked;
    for (size_t i = 0; i < description.number_of_mediasections(); ++i) {
      const auto *candidates = description.candidates(i);
      for (size_t j = 0; (candidates != nullptr) && j < candidates->count(); ++j) {
        const auto *candidate = candidates->at(j);
        if (isBlockedCandidate(candidate->candidate())) {
          blocked.push_back(
              webrtc::CreateIceCandidate(candidate->sdp_mid(), candidate->sdp_mline_index(), candidate->candidate()));
        }
      }
    }
    for (const auto &candidate : blocked) {
      description.RemoveCandidate(candidate.get());
    }
  }

  std::unique_ptr<webrtc::SessionDescriptionInterface> parseDescription(const RTCSessionDescriptionInit &init,
                                                                        std::optional<RTCCallbackException> &error) {
    webrtc::SdpParseError parseError;
    auto description = webrtc::CreateSessionDescription(init.type, init.sdp, &parseError);
    if (!description) {
      webrtc::RTCError rtcError(webrtc::RTCErrorType::OPERATION_ERROR_WITH_DATA,
                                "Failed to parse the session description: " + parseError.description +
                                    (parseError.line.empty() ? "" : " (" + parseError.line + ")"));
      rtcError.set_error_detail(webrtc::RTCErrorDetailType::SDP_SYNTAX_ERROR);
      error.emplace(std::move(rtcError), lineNumber(init.sdp, parseError.line));
    }
    return description;
  }

  std::vector<IceCandidateInit> endOfCandidates(const webrtc::SessionDescriptionInterface *description) {
    std::vector<IceCandidateInit> result;
    if (description == nullptr) {
      return result;
    }
    const auto *session = description->description();
    const auto *bundle = session->GetGroupByName(static_cast<const char *>(webrtc::GROUP_TYPE_BUNDLE));
    bool bundleDone = false;
    int index = 0;
    for (const auto &content : session->contents()) {
      auto mid = content.mid();
      const bool bundled = (bundle != nullptr) && bundle->HasContentName(mid);
      if (!content.rejected && !(bundled && bundleDone)) {
        const auto *transport = session->GetTransportInfoByName(mid);
        std::optional<std::string> ufrag;
        if ((transport != nullptr) && !transport->description.ice_ufrag.empty()) {
          ufrag = transport->description.ice_ufrag;
        }
        result.emplace_back(mid, index, ufrag);
        bundleDone = bundleDone || bundled;
      }
      ++index;
    }
    return result;
  }

  std::string addEndOfCandidates(const std::string &sdp, const std::set<std::string> *mids) {
    std::string result;
    bool inMedia = false;
    bool rejected = false;
    bool ended = false;
    std::string mid;
    auto endSection = [&]() {
      if (inMedia && !rejected && !ended && (!mids || mids->contains(mid))) {
        result += "a=end-of-candidates\r\n";
      }
    };
    size_t pos = 0;
    while (pos < sdp.size()) {
      auto end = sdp.find("\r\n", pos);
      auto line = sdp.substr(pos, end == std::string::npos ? std::string::npos : end - pos);
      if (line.starts_with("m=")) {
        endSection();
        inMedia = true;
        ended = false;
        // a rejected media section has port 0
        auto space = line.find(' ');
        rejected = space != std::string::npos && line.compare(space + 1, 2, "0 ") == 0;
        mid.clear();
      } else if (line == "a=end-of-candidates") {
        ended = true;
      } else if (line.starts_with(kMidPrefix)) {
        mid = line.substr(kMidPrefix.size());
      }
      result += line + "\r\n";
      if (end == std::string::npos) {
        break;
      }
      pos = end + 2;
    }
    endSection();
    return result;
  }

  std::optional<RTCCallbackException> candidateSections(const webrtc::SessionDescriptionInterface *remote,
                                                        const std::optional<std::string> &sdpMid,
                                                        std::optional<int> sdpMLineIndex,
                                                        const std::optional<std::string> &usernameFragment,
                                                        std::set<std::string> &mids) {
    if (remote == nullptr) {
      return RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The remote description was null");
    }
    const auto *session = remote->description();
    const auto &contents = session->contents();
    for (size_t i = 0; i < contents.size(); ++i) {
      bool matches = true;
      if (sdpMid) {
        matches = contents[i].mid() == *sdpMid;
      } else if (sdpMLineIndex) {
        matches = std::cmp_equal(i, *sdpMLineIndex);
      }
      if (matches && !contents[i].rejected) {
        mids.insert(contents[i].mid());
      }
    }
    if (mids.empty() && (sdpMid || sdpMLineIndex)) {
      return RTCCallbackException(webrtc::RTCErrorType::UNSUPPORTED_OPERATION,
                                  "The media section of the candidate was not found");
    }
    if (usernameFragment) {
      const bool known = std::ranges::any_of(mids, [&](const std::string &mid) {
        const auto *transport = session->GetTransportInfoByName(mid);
        return transport != nullptr && transport->description.ice_ufrag == *usernameFragment;
      });
      if (!known) {
        return RTCCallbackException(webrtc::RTCErrorType::UNSUPPORTED_OPERATION,
                                    "The usernameFragment doesn't match the remote description");
      }
    }
    return std::nullopt;
  }

} // namespace python_webrtc
