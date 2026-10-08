//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_FIELD_TRIALS_H_
#define PYTHON_WEBRTC_UTILS_FIELD_TRIALS_H_

#include <map>
#include <memory>
#include <string>
#include <string_view>

#include <api/field_trials_view.h>

namespace python_webrtc {

  // "Name/Group/" pairs, like webrtc::FieldTrials, which the prebuilt libwebrtc lacks
  class FieldTrials : public webrtc::FieldTrialsView {
  public:
    // nullptr if malformed, or if a trial repeats with another group
    static std::unique_ptr<FieldTrials> Parse(std::string_view trials) {
      auto result = std::make_unique<FieldTrials>();
      while (!trials.empty()) {
        const auto name = Next(trials);
        const auto group = Next(trials);
        if (name.empty() || group.empty()) {
          return nullptr;
        }
        const auto [it, inserted] = result->_trials.emplace(name, group);
        if (!inserted && it->second != group) {
          return nullptr;
        }
      }
      return result;
    }

    [[nodiscard]] std::string Lookup(absl::string_view key) const override {
      const auto it = _trials.find(std::string(key));
      return it == _trials.end() ? std::string() : it->second;
    }

    [[nodiscard]] std::unique_ptr<webrtc::FieldTrialsView> CreateCopy() const override {
      return std::make_unique<FieldTrials>(*this);
    }

  private:
    // consumes the text up to the next '/'
    static std::string_view Next(std::string_view &trials) {
      const auto end = trials.find('/');
      if (end == std::string_view::npos) {
        trials = {};
        return {};
      }
      const auto part = trials.substr(0, end);
      trials.remove_prefix(end + 1);
      return part;
    }

    std::map<std::string, std::string> _trials;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_FIELD_TRIALS_H_
