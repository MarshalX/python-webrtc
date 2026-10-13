//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include <rtc/rtc.hpp>

using Clock = std::chrono::steady_clock;

// A data channel that counts what it receives, and echoes, floods or pings.
class Channel : public std::enable_shared_from_this<Channel> {
public:
  explicit Channel(std::shared_ptr<rtc::DataChannel> dc);

  // Sets the callbacks of the data channel, which hold the channel until reset().
  void watch();
  void reset();

  int64_t bytes() const { return bytes_.load(); }
  int64_t messages() const { return messages_.load(); }
  void echo() { echo_.store(true); }

  // Sends messages for a while, keeping the buffered amount between the watermarks.
  void flood(size_t size, Clock::duration duration, size_t low, size_t high);
  // Sends numbered messages at a rate to an echoing peer; their round trip times in ms.
  std::vector<double> ping(size_t size, double rate, Clock::duration duration);

private:
  void onMessage(const rtc::binary &data);
  void onLow();
  void answer(uint32_t number);
  // waits for a signal of bufferedamountlow until the deadline
  void waitLow(Clock::time_point deadline);
  void waitAnswers(Clock::duration timeout);

  std::shared_ptr<rtc::DataChannel> dc_;
  std::atomic<int64_t> bytes_{0};
  std::atomic<int64_t> messages_{0};
  std::atomic<bool> echo_{false};
  std::atomic<bool> pinging_{false};

  std::mutex mu_;
  std::condition_variable changed_;
  // a bufferedamountlow not waited for yet: one that fires before the flood waits isn't lost
  bool low_ = false;
  std::map<uint32_t, Clock::time_point> pings_;
  std::vector<double> rtts_;
};
