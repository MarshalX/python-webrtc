//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_STATS_COLLECTOR_CALLBACK_H_
#define PYTHON_WEBRTC_INTERFACES_STATS_COLLECTOR_CALLBACK_H_

#include <functional>
#include <set>
#include <string>

#include <api/stats/rtc_stats_collector_callback.h>
#include <api/stats/rtc_stats_report.h>

namespace python_webrtc {

  // Delivers a stats report as JSON, which Python turns into webrtc.RTCStatsReport
  class StatsCollectorCallback : public webrtc::RTCStatsCollectorCallback {
  public:
    // Stats of the types in excluded are left out
    explicit StatsCollectorCallback(std::function<void(std::string)> onDelivered, std::set<std::string> excluded = {})
        : _onDelivered(std::move(onDelivered)), _excluded(std::move(excluded)) {}

    void OnStatsDelivered(const webrtc::scoped_refptr<const webrtc::RTCStatsReport> &report) override {
      if (_excluded.empty()) {
        _onDelivered(report->ToJson());
        return;
      }
      auto filtered = webrtc::RTCStatsReport::Create(report->timestamp());
      for (const auto &stats : *report) {
        if (!_excluded.contains(stats.type())) {
          filtered->AddStats(stats.copy());
        }
      }
      _onDelivered(filtered->ToJson());
    }

  private:
    std::function<void(std::string)> _onDelivered;
    std::set<std::string> _excluded;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_STATS_COLLECTOR_CALLBACK_H_
