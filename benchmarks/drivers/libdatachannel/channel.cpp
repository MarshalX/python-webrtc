//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

#include "channel.hpp"

#include <thread>
#include <variant>

namespace {

  constexpr auto pingDrain = std::chrono::seconds(1);

  uint32_t readNumber(const rtc::binary &data) {
    return (std::to_integer<uint32_t>(data[0]) << 24) | (std::to_integer<uint32_t>(data[1]) << 16) |
           (std::to_integer<uint32_t>(data[2]) << 8) | std::to_integer<uint32_t>(data[3]);
  }

  void writeNumber(rtc::binary &data, uint32_t number) {
    for (int i = 0; i < 4; ++i) {
      data[i] = std::byte(number >> (24 - 8 * i));
    }
  }

  double millisecondsSince(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
  }

} // namespace

Channel::Channel(std::shared_ptr<rtc::DataChannel> dc) : dc_(std::move(dc)) {}

void Channel::watch() {
  auto self = shared_from_this();
  dc_->onMessage([self](rtc::binary data) { self->onMessage(data); }, [](rtc::string) {});
  dc_->onBufferedAmountLow([self] { self->onLow(); });
}

void Channel::reset() {
  dc_->resetCallbacks();
}

void Channel::onMessage(const rtc::binary &data) {
  bytes_ += int64_t(data.size());
  ++messages_;
  if (echo_.load()) {
    dc_->send(data);
  }
  if (pinging_.load() && data.size() >= 4) {
    answer(readNumber(data));
  }
}

void Channel::onLow() {
  {
    std::lock_guard lock(mu_);
    low_ = true;
  }
  changed_.notify_all();
}

void Channel::answer(uint32_t number) {
  {
    std::lock_guard lock(mu_);
    auto sent = pings_.find(number);
    if (sent == pings_.end()) {
      return;
    }
    rtts_.push_back(millisecondsSince(sent->second));
    pings_.erase(sent);
  }
  changed_.notify_all();
}

void Channel::waitLow(Clock::time_point deadline) {
  std::unique_lock lock(mu_);
  changed_.wait_until(lock, deadline, [this] { return low_; });
  low_ = false;
}

void Channel::flood(size_t size, Clock::duration duration, size_t low, size_t high) {
  dc_->setBufferedAmountLowThreshold(low);
  const rtc::binary payload(size);
  const auto deadline = Clock::now() + duration;

  while (Clock::now() < deadline) {
    if (dc_->bufferedAmount() >= high) {
      waitLow(deadline);
      continue;
    }

    dc_->send(payload.data(), payload.size());
  }
}

void Channel::waitAnswers(Clock::duration timeout) {
  std::unique_lock lock(mu_);
  changed_.wait_for(lock, timeout, [this] { return pings_.empty(); });
  pings_.clear();
}

std::vector<double> Channel::ping(size_t size, double rate, Clock::duration duration) {
  {
    std::lock_guard lock(mu_);
    rtts_.clear();
  }
  pinging_.store(true);
  const auto start = Clock::now();
  const auto count = int64_t(rate * std::chrono::duration<double>(duration).count() + 0.5);

  for (int64_t number = 0; number < count; ++number) {
    std::this_thread::sleep_until(
        start + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(double(number) / rate)));
    rtc::binary payload(size);
    writeNumber(payload, uint32_t(number));
    {
      std::lock_guard lock(mu_);
      pings_[uint32_t(number)] = Clock::now();
    }
    dc_->send(payload.data(), payload.size());
  }

  waitAnswers(pingDrain);
  pinging_.store(false);
  std::lock_guard lock(mu_);
  return rtts_;
}
