//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "mailbox.h"

#include "dispatcher.h"
#include "gil.h"
#include "libwebrtc_thread.h"
#include "parking.h"

#include <array>
#include <atomic>

#ifndef _WIN32
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#endif

#ifdef __linux__
#include <sys/eventfd.h>
#endif

#include <pybind11/stl.h>

namespace python_webrtc {

  namespace {
    std::atomic<uint64_t> &NextMailboxId() {
      static std::atomic<uint64_t> next{1};
      return next;
    }

#ifdef _WIN32
    // no loop on Windows can watch an fd, so its mailboxes have none
    std::optional<Mailbox::WakeEnds> OpenWake() {
      return std::nullopt;
    }

    void WriteWake(int /*channel*/) {}

    void ReadWakes(int /*channel*/) {}

    void CloseWake(const Mailbox::WakeEnds & /*ends*/) {}
#else
#ifdef __linux__
    // an eventfd adds up wakes in an 8-byte count
    using WakeUnit = uint64_t;

    std::optional<Mailbox::WakeEnds> OpenWake() {
      const int channel = ::eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
      if (channel < 0) {
        return std::nullopt;
      }
      return Mailbox::WakeEnds{.read = channel, .write = channel};
    }
#else
    using WakeUnit = char;

    // NOLINTBEGIN(cppcoreguidelines-pro-type-vararg): fcntl's flags
    void SetNonBlocking(int end) {
      (void)::fcntl(end, F_SETFL, ::fcntl(end, F_GETFL) | O_NONBLOCK);
      (void)::fcntl(end, F_SETFD, FD_CLOEXEC);
    }

    void SetNoSigPipe([[maybe_unused]] int end) {
#ifdef F_SETNOSIGPIPE
      (void)::fcntl(end, F_SETNOSIGPIPE, 1);
#endif
    }
    // NOLINTEND(cppcoreguidelines-pro-type-vararg)

    std::optional<Mailbox::WakeEnds> OpenWake() {
      std::array<int, 2> ends{};
      if (::pipe(ends.data()) != 0) {
        return std::nullopt;
      }
      for (const int end : ends) {
        SetNonBlocking(end);
      }
      SetNoSigPipe(ends[1]);
      return Mailbox::WakeEnds{.read = ends[0], .write = ends[1]};
    }
#endif

    // EAGAIN: a full channel wakes the loop already
    void WriteWake(int channel) {
      const WakeUnit unit = 1;
      while (::write(channel, &unit, sizeof(unit)) < 0 && errno == EINTR) {
      }
    }

    void ReadWakes(int channel) {
      constexpr size_t kUnits = 64;
      std::array<WakeUnit, kUnits> units{};
      const auto full = static_cast<ssize_t>(sizeof(units));
      while (true) {
        // NOLINTNEXTLINE(clang-analyzer-unix.BlockInCriticalSection): non-blocking
        const ssize_t got = ::read(channel, units.data(), sizeof(units));
        const bool interrupted = got < 0 && errno == EINTR;
        if (got != full && !interrupted) {
          return;
        }
      }
    }

    void CloseWake(const Mailbox::WakeEnds &ends) {
      if (ends.write != ends.read) {
        (void)::close(ends.write);
      }
      (void)::close(ends.read);
    }
#endif
  } // namespace

  Mailbox::Mailbox() : _id(NextMailboxId()++) {}

  Mailbox::~Mailbox() {
    CloseWakeLocked();
  }

  void Mailbox::Post(Record record) {
    CheckNativeThreadDetached("Mailbox::Post");
    Parking::At("mailbox.post");
    const bool direct = !Parking::Holds("dispatcher.wake");

    bool wake = false;
    {
      const std::scoped_lock lock(_mutex);
      if (_closed) {
        _dropped++;
      } else {
        wake = !_awake;
        _awake = true;
        _records.push_back(std::move(record));
        const WakeEnds *ends = wake && direct ? WakeLocked() : nullptr;
        if (ends != nullptr) {
          WriteWake(ends->write);
          wake = false;
        }
      }
    }

    // a dropped record is released here, outside the lock
    if (wake) {
      Dispatcher::Wake(_id);
    }
  }

  std::optional<int> Mailbox::EnableWake() {
    const std::scoped_lock lock(_mutex);
    if (_closed) {
      return std::nullopt;
    }
    if (!_wake) {
      _wake = OpenWake();
      _wakeForks = Forks().load();
    }
    const WakeEnds *ends = WakeLocked();
    return ends != nullptr ? std::optional(ends->read) : std::nullopt;
  }

  bool Mailbox::AckWake() {
    const std::scoped_lock lock(_mutex);
    const WakeEnds *ends = WakeLocked();
    if (ends == nullptr) {
      return false;
    }
    ReadWakes(ends->read);
    return true;
  }

  void Mailbox::DisableWake() {
    const std::scoped_lock lock(_mutex);
    CloseWakeLocked();
  }

  const Mailbox::WakeEnds *Mailbox::WakeLocked() const {
    return _wake.has_value() && _wakeForks == Forks().load() ? &*_wake : nullptr;
  }

  void Mailbox::CloseWakeLocked() {
    if (_wake) {
      CloseWake(*_wake);
      _wake.reset();
    }
  }

  void Mailbox::PostMarker(uint64_t key) {
    Post(Record{.token = key});
  }

  pybind11::object Mailbox::Take() {
    while (true) {
      Record record;
      {
        const std::scoped_lock lock(_mutex);
        if (_records.empty()) {
          // the loop drains until a take finds nothing, so the next post wakes it
          _awake = false;
          return pybind11::none();
        }
        record = std::move(_records.front());
        _records.pop_front();
      }
      // converted outside the lock
      pybind11::object args = pybind11::none();
      if (record.args) {
        bool converted = false;
        CallUnraisable("Mailbox.take", [&]() {
          args = record.args();
          converted = true;
        });
        if (!converted) {
          continue;
        }
      }
      const pybind11::object name =
          record.name != nullptr ? pybind11::object(pybind11::str(record.name)) : pybind11::object(pybind11::none());
      return pybind11::make_tuple(name, record.token, record.failed, args);
    }
  }

  void Mailbox::Close() {
    std::deque<Record> dropped;
    {
      const std::scoped_lock lock(_mutex);
      _closed = true;
      dropped.swap(_records);
      _dropped += dropped.size();
      CloseWakeLocked();
    }
    // dropped here, outside the lock
  }

  bool Mailbox::Closed() const {
    const std::scoped_lock lock(_mutex);
    return _closed;
  }

  uint64_t Mailbox::Dropped() const {
    const std::scoped_lock lock(_mutex);
    return _dropped;
  }

  size_t Mailbox::Size() const {
    const std::scoped_lock lock(_mutex);
    return _records.size();
  }

  void Mailbox::Init(pybind11::module &m) {
    pybind11::class_<Mailbox, std::shared_ptr<Mailbox>>(m, "Mailbox")
        .def(pybind11::init<>())
        .def_property_readonly("id", &Mailbox::Id)
        .def("take", &Mailbox::Take)
        .def("enableWake", &Mailbox::EnableWake)
        .def("ackWake", &Mailbox::AckWake)
        .def("disableWake", &Mailbox::DisableWake)
        .def("close", &Mailbox::Close, nogil())
        .def_property_readonly("closed", &Mailbox::Closed)
        .def_property_readonly("dropped", &Mailbox::Dropped)
        .def("postMarker", &Mailbox::PostMarker, nogil(), pybind11::arg("key"))
        .def("__len__", &Mailbox::Size);
    Binding::Init(m);
  }

  bool Binding::Bind(std::shared_ptr<Mailbox> mailbox) {
    if (!mailbox) {
      return false;
    }
    const std::scoped_lock lock(_mutex);
    if (_mailbox && !_mailbox->Closed()) {
      return false;
    }
    _mailbox = std::move(mailbox);
    return true;
  }

  void Binding::Inherit(const Binding &parent) {
    (void)Bind(parent.mailbox());
  }

  void Binding::Unbind() {
    std::shared_ptr<Mailbox> unbound;
    {
      const std::scoped_lock lock(_mutex);
      unbound.swap(_mailbox);
    }
  }

  bool Binding::IsBound() const {
    const std::scoped_lock lock(_mutex);
    return _mailbox && !_mailbox->Closed();
  }

  bool Binding::IsOrphaned() const {
    const std::scoped_lock lock(_mutex);
    return _mailbox && _mailbox->Closed();
  }

  void Binding::Post(Record record) const {
    if (auto bound = mailbox()) {
      bound->Post(std::move(record));
    }
  }

  std::shared_ptr<Mailbox> Binding::mailbox() const {
    const std::scoped_lock lock(_mutex);
    return _mailbox;
  }

  std::optional<uint64_t> Binding::MailboxId() const {
    auto bound = mailbox();
    if (!bound || bound->Closed()) {
      return std::nullopt;
    }
    return bound->Id();
  }

  void Binding::Init(pybind11::module &m) {
    pybind11::class_<Binding, std::shared_ptr<Binding>>(m, "Binding");
  }

  Completion::Completion(std::shared_ptr<Mailbox> mailbox, uint64_t token)
      : _mailbox(std::move(mailbox)), _token(token) {}

  Completion::~Completion() {
    if (_mailbox) {
      Fail(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The operation was abandoned"));
    }
  }

  Completion::Completion(Completion &&other) noexcept : _mailbox(std::move(other._mailbox)), _token(other._token) {
    other._mailbox = nullptr;
  }

  void Completion::Fail(RTCCallbackException error) {
    Settle(true, [error = std::move(error)]() { return pybind11::make_tuple(error.ToPython()); });
  }

  void Completion::Settle(bool failed, std::function<pybind11::tuple()> args) {
    std::shared_ptr<Mailbox> settled;
    settled.swap(_mailbox);
    if (settled) {
      settled->Post(Record{.token = _token, .failed = failed, .args = std::move(args)});
    }
  }

} // namespace python_webrtc
