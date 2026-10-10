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

#include <atomic>

#include <pybind11/stl.h>

namespace python_webrtc {

  namespace {
    std::atomic<uint64_t> &NextMailboxId() {
      static std::atomic<uint64_t> next{1};
      return next;
    }
  } // namespace

  Mailbox::Mailbox() : _id(NextMailboxId()++) {}

  void Mailbox::Post(Record record) {
    CheckNativeThreadDetached("Mailbox::Post");
    Parking::At("mailbox.post");
    bool wake = false;
    {
      const std::scoped_lock lock(_mutex);
      if (_closed) {
        _dropped++;
      } else {
        wake = _records.empty();
        _records.push_back(std::move(record));
      }
    }
    // a dropped record is released here, outside the lock
    if (wake) {
      Dispatcher::Wake(_id);
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

  Completion &Completion::operator=(Completion &&other) noexcept {
    if (this != &other) {
      _mailbox = std::move(other._mailbox);
      _token = other._token;
      other._mailbox = nullptr;
    }
    return *this;
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
