//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_STATS_COLLECTOR_CALLBACK_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_STATS_COLLECTOR_CALLBACK_H_

#include <map>
#include <memory>
#include <string>
#include <utility>

#include <api/stats/rtc_stats_collector_callback.h>
#include <api/stats/rtc_stats_report.h>
#include <api/stats/rtcstats_objects.h>

#include "../../utils/mailbox.h"

namespace python_webrtc {

  // Delivers a stats report as JSON, which Python turns into webrtc.RTCStatsReport
  class StatsCollectorCallback : public webrtc::RTCStatsCollectorCallback {
  public:
    // remoteTrackIds by mid: libwebrtc drops trackIdentifier once a transceiver stops
    explicit StatsCollectorCallback(Completion completion, std::map<std::string, std::string> remoteTrackIds = {})
        : _completion(std::move(completion)), _remoteTrackIds(std::move(remoteTrackIds)) {}

    void OnStatsDelivered(const webrtc::scoped_refptr<const webrtc::RTCStatsReport> &report) override {
      webrtc::scoped_refptr<webrtc::RTCStatsReport> completed;
      for (const auto *inbound : report->GetStatsOfType<webrtc::RTCInboundRtpStreamStats>()) {
        const auto trackId = inbound->mid ? _remoteTrackIds.find(*inbound->mid) : _remoteTrackIds.end();
        if (inbound->track_identifier || trackId == _remoteTrackIds.end()) {
          continue;
        }
        auto stats = std::make_unique<webrtc::RTCInboundRtpStreamStats>(*inbound);
        stats->track_identifier = trackId->second;
        if (!completed) {
          completed = report->Copy();
        }
        completed->Take(stats->id());
        completed->AddStats(std::move(stats));
      }
      _completion.Succeed(completed ? completed->ToJson() : report->ToJson());
    }

  private:
    Completion _completion;
    std::map<std::string, std::string> _remoteTrackIds;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_PEER_CONNECTION_STATS_COLLECTOR_CALLBACK_H_
