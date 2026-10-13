//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

// The driver of libdatachannel for the benchmarks, speaking benchmarks/protocol.py; data channels only.

#include <cstdlib>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

#if defined(__APPLE__)
#include <malloc/malloc.h>
#elif defined(__GLIBC__)
#include <malloc.h>
#endif

#include <nlohmann/json.hpp>
#include <rtc/rtc.hpp>
#include <rtc/version.h>

#include "channel.hpp"

using json = nlohmann::json;

namespace {

  const std::string dataChannelLabel = "bench";

  struct Peer {
    std::shared_ptr<rtc::PeerConnection> pc;
    bool trickle = false;
    std::shared_ptr<Channel> channel;

    std::mutex mu;
    std::condition_variable changed;
    bool gathered = false;
  };

  class Driver {
  public:
    Driver() : origin_(Clock::now()) {}

    json handle(const json &c);
    void send(const json &m);

  private:
    double now() const { return std::chrono::duration<double>(Clock::now() - origin_).count(); }
    void emit(int pc, const std::string &name);
    std::shared_ptr<Peer> peer(int pc);
    std::shared_ptr<Channel> channel(int pc);

    json create(const json &c);
    void watch(int id, const std::shared_ptr<Peer> &p);
    void watchChannel(int id, const std::shared_ptr<Peer> &p, std::shared_ptr<rtc::DataChannel> dc);
    std::string setLocal(Peer &p, rtc::Description::Type type);
    json offer(const json &c);
    json answer(const json &c);
    json accept(const json &c);
    json addCandidate(const json &c);
    json close(const json &c);
    json count(const json &c);
    json echo(const json &c);
    json flood(const json &c);
    json ping(const json &c);

    const Clock::time_point origin_;
    std::mutex outMu_;
    std::mutex mu_;
    std::map<int, std::shared_ptr<Peer>> peers_;
    std::set<std::pair<int, std::string>> sent_;
  };

  Clock::duration seconds(double value) {
    return std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(value));
  }

  void Driver::send(const json &m) {
    std::lock_guard lock(outMu_);
    std::cout << m.dump() << '\n' << std::flush;
  }

  void Driver::emit(int pc, const std::string &name) {
    {
      std::lock_guard lock(mu_);
      if (!sent_.insert({pc, name}).second) {
        return;
      }
    }
    send({{"event", name}, {"pc", pc}, {"t", now()}});
  }

  std::shared_ptr<Peer> Driver::peer(int pc) {
    std::lock_guard lock(mu_);
    auto found = peers_.find(pc);
    if (found == peers_.end()) {
      throw std::runtime_error("no connection " + std::to_string(pc));
    }
    return found->second;
  }

  std::shared_ptr<Channel> Driver::channel(int pc) {
    auto p = peer(pc);
    std::lock_guard lock(mu_);
    if (!p->channel) {
      throw std::runtime_error("no open data channel on connection " + std::to_string(pc));
    }
    return p->channel;
  }

  json hello() {
    return {{"library", "libdatachannel"}, {"version", RTC_VERSION}, {"trickle", true}};
  }

  json Driver::create(const json &c) {
    const double start = now();
    const int id = c.at("pc");
    rtc::Configuration config;
    config.disableAutoNegotiation = true;
    auto p = std::make_shared<Peer>();
    p->pc = std::make_shared<rtc::PeerConnection>(config);
    p->trickle = c.value("trickle", false);
    {
      std::lock_guard lock(mu_);
      peers_[id] = p;
    }
    watch(id, p);

    if (c.at("role") == "offerer") {
      rtc::DataChannelInit init;
      init.reliability.unordered = !c.value("ordered", true);
      watchChannel(id, p, p->pc->createDataChannel(dataChannelLabel, init));
    } else {
      p->pc->onDataChannel([this, id, weak = std::weak_ptr(p)](std::shared_ptr<rtc::DataChannel> dc) {
        if (auto p = weak.lock()) {
          watchChannel(id, p, std::move(dc));
        }
      });
    }

    return {{"t_start", start}, {"t_end", now()}};
  }

  void Driver::watch(int id, const std::shared_ptr<Peer> &p) {
    using Pc = rtc::PeerConnection;
    p->pc->onIceStateChange([this, id](Pc::IceState state) {
      if (state == Pc::IceState::Connected || state == Pc::IceState::Completed) {
        emit(id, "ice_connected");
      }
    });

    p->pc->onStateChange([this, id](Pc::State state) {
      if (state == Pc::State::Connected) {
        emit(id, "connected");
      } else if (state == Pc::State::Failed) {
        emit(id, "failed");
      }
    });

    p->pc->onGatheringStateChange([this, id, weak = std::weak_ptr(p)](Pc::GatheringState state) {
      auto p = weak.lock();
      if (state != Pc::GatheringState::Complete || !p) {
        return;
      }
      {
        std::lock_guard lock(p->mu);
        p->gathered = true;
      }
      p->changed.notify_all();
      emit(id, "gathered");
    });

    p->pc->onLocalCandidate([this, id, trickle = p->trickle](rtc::Candidate candidate) {
      if (!trickle) {
        return;
      }
      json init = {{"candidate", candidate.candidate()}, {"sdpMid", candidate.mid()}, {"sdpMLineIndex", 0}};
      send({{"event", "candidate"}, {"pc", id}, {"t", now()}, {"candidate", init}});
    });
  }

  void Driver::watchChannel(int id, const std::shared_ptr<Peer> &p, std::shared_ptr<rtc::DataChannel> dc) {
    auto c = std::make_shared<Channel>(dc);
    c->watch();
    auto opened = [this, id, weak = std::weak_ptr(p), c] {
      if (auto p = weak.lock()) {
        std::lock_guard lock(mu_);
        p->channel = c;
      }
      emit(id, "dc_open");
    };

    dc->onOpen(opened);
    if (dc->isOpen()) {
      opened();
    }
  }

  // setLocal sets a local description and returns its SDP, with the candidates unless they trickle.
  std::string Driver::setLocal(Peer &p, rtc::Description::Type type) {
    p.pc->setLocalDescription(type);
    if (!p.trickle) {
      std::unique_lock lock(p.mu);
      p.changed.wait(lock, [&p] { return p.gathered; });
    }
    return std::string(*p.pc->localDescription());
  }

  json Driver::offer(const json &c) {
    auto p = peer(c.at("pc"));
    const double start = now();
    // libdatachannel creates and sets a description in one call, so the offer is timed once set
    auto sdp = setLocal(*p, rtc::Description::Type::Offer);
    return {{"sdp", sdp}, {"t_start", start}, {"t_offer", now()}};
  }

  json Driver::answer(const json &c) {
    auto p = peer(c.at("pc"));
    p->pc->setRemoteDescription(rtc::Description(c.at("sdp").get<std::string>(), rtc::Description::Type::Offer));
    return {{"sdp", setLocal(*p, rtc::Description::Type::Answer)}};
  }

  json Driver::accept(const json &c) {
    auto p = peer(c.at("pc"));
    p->pc->setRemoteDescription(rtc::Description(c.at("sdp").get<std::string>(), rtc::Description::Type::Answer));
    return json::object();
  }

  json Driver::addCandidate(const json &c) {
    auto p = peer(c.at("pc"));
    const json &init = c.at("candidate");
    auto candidate = init.value("candidate", std::string());
    // an empty candidate ends the candidates, which libdatachannel doesn't need
    if (!candidate.empty()) {
      auto mid = init.contains("sdpMid") && init["sdpMid"].is_string() ? init["sdpMid"].get<std::string>() : "0";
      p->pc->addRemoteCandidate(rtc::Candidate(candidate, mid));
    }
    return json::object();
  }

  json Driver::close(const json &c) {
    const int id = c.at("pc");
    auto p = peer(id);
    std::shared_ptr<Channel> channel;
    {
      std::lock_guard lock(mu_);
      peers_.erase(id);
      channel = std::exchange(p->channel, nullptr);
    }

    p->pc->close();
    // the callbacks hold the channels and the driver: dropped so that the connection is freed
    p->pc->resetCallbacks();
    if (channel) {
      channel->reset();
    }
    return json::object();
  }

  json Driver::count(const json &c) {
    auto ch = channel(c.at("pc"));
    return {{"bytes", ch->bytes()}, {"messages", ch->messages()}, {"t", now()}};
  }

  json Driver::echo(const json &c) {
    channel(c.at("pc"))->echo();
    return json::object();
  }

  json Driver::flood(const json &c) {
    channel(c.at("pc"))->flood(c.at("size"), seconds(c.at("seconds")), c.at("low"), c.at("high"));
    return json::object();
  }

  json Driver::ping(const json &c) {
    auto ch = channel(c.at("pc"));
    return {{"rtts_ms", ch->ping(c.at("size"), c.at("rate"), seconds(c.at("seconds")))}};
  }

  json collect() {
#if defined(__APPLE__)
    malloc_zone_pressure_relief(nullptr, 0);
#elif defined(__GLIBC__)
    malloc_trim(0);
#endif
    return json::object();
  }

  json Driver::handle(const json &c) {
    const std::string cmd = c.at("cmd");
    if (cmd == "hello") {
      return hello();
    }
    if (cmd == "create") {
      return create(c);
    }
    if (cmd == "offer") {
      return offer(c);
    }
    if (cmd == "answer") {
      return answer(c);
    }
    if (cmd == "accept") {
      return accept(c);
    }
    if (cmd == "add_candidate") {
      return addCandidate(c);
    }
    if (cmd == "count") {
      return count(c);
    }
    if (cmd == "echo") {
      return echo(c);
    }
    if (cmd == "flood") {
      return flood(c);
    }
    if (cmd == "ping") {
      return ping(c);
    }
    if (cmd == "close") {
      return close(c);
    }
    if (cmd == "collect") {
      return collect();
    }
    if (cmd == "probe") {
      return json::object(); // no event loop to lag
    }
    throw std::runtime_error("unknown command " + cmd);
  }

  void run(Driver &d, const json &c) {
    try {
      d.send({{"id", c.at("id")}, {"result", d.handle(c)}});
    } catch (const std::exception &error) {
      d.send({{"id", c.value("id", -1)}, {"error", error.what()}});
    }
  }

} // namespace

int main() {
  rtc::InitLogger(rtc::LogLevel::Error, [](rtc::LogLevel, std::string message) { std::cerr << message << std::endl; });
  Driver d;
  std::string line;
  while (std::getline(std::cin, line)) {
    auto c = json::parse(line, nullptr, false);
    if (!c.is_object() || !c.contains("cmd")) {
      continue;
    }
    if (c["cmd"] == "exit") {
      d.send({{"id", c.value("id", -1)}, {"result", json::object()}});
      // exits without tearing down the connections left: the runner is done with them
      std::_Exit(0);
    }
    std::thread(run, std::ref(d), std::move(c)).detach();
  }
  std::_Exit(0);
}
