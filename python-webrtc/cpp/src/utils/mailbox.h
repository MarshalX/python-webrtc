//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_MAILBOX_H_
#define PYTHON_WEBRTC_UTILS_MAILBOX_H_

#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <utility>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../exceptions.h"
#include "libwebrtc_thread.h"

namespace python_webrtc {

  struct Record {
    std::shared_ptr<void> source;
    uint64_t target = 0;
    // nullptr for a completion or a marker
    const char *name = nullptr;
    uint64_t token = 0;
    bool failed = false;
    // runs on the loop thread; an event's target comes first
    std::function<pybind11::tuple()> args;
  };

  class Mailbox : public std::enable_shared_from_this<Mailbox> {
  public:
    Mailbox();

    [[nodiscard]] uint64_t Id() const { return _id; }

    void Post(Record record);

    void PostMarker(uint64_t key);

    // (name|None, token, failed, args|None) or None; an unconvertible record is reported and skipped
    pybind11::object Take();

    void Close();

    [[nodiscard]] bool Closed() const;

    [[nodiscard]] uint64_t Dropped() const;

    [[nodiscard]] size_t Size() const;

    static void Init(pybind11::module &m);

  private:
    const uint64_t _id;
    mutable std::mutex _mutex;
    std::deque<Record> _records;
    bool _closed = false;
    uint64_t _dropped = 0;
  };

  class Binding {
  public:
    // the first binding wins until its mailbox closes
    bool Bind(std::shared_ptr<Mailbox> mailbox);

    void Inherit(const Binding &parent);

    void Unbind();

    [[nodiscard]] bool IsBound() const;

    void Post(Record record) const;

    [[nodiscard]] std::shared_ptr<Mailbox> mailbox() const;

    [[nodiscard]] std::optional<uint64_t> MailboxId() const;

    static void Init(pybind11::module &m);

  private:
    // read on libwebrtc threads, written on Python threads
    mutable std::mutex _mutex;
    std::shared_ptr<Mailbox> _mailbox;
  };

  // on the class, not the pybind base: a base method costs a derived-to-base cast per call
  template <typename Class>
  Class DefineBinding(Class cls) {
    using T = Class::type;
    cls.def(
           "_bind", [](T &self, std::shared_ptr<Mailbox> mailbox) { return self.Bind(std::move(mailbox)); },
           pybind11::arg("mailbox"))
        .def_property_readonly("_bound", [](const T &self) { return self.IsBound(); })
        .def_property_readonly("_mailbox", [](const T &self) { return self.MailboxId(); });
    return cls;
  }

  template <typename T>
  class Emitter : public Binding {
  protected:
    template <typename... Args>
    void Emit(const char *name, const Args &...args) {
      CheckNativeThreadDetached("Emitter::Emit");
      if (!IsBound()) {
        return;
      }
      // nothing keeps it for the record while its constructor runs
      auto self = static_cast<T *>(this)->weak_from_this().lock();
      if (!self) {
        return;
      }
      Post(Record{.source = self, .target = self->Id(), .name = name, .args = [self, args...]() {
                    return pybind11::make_tuple(self, args...);
                  }});
    }

  private:
    friend T;

    Emitter() = default;
  };

  class Completion {
  public:
    Completion(std::shared_ptr<Mailbox> mailbox, uint64_t token);

    ~Completion();

    Completion(Completion &&other) noexcept;
    Completion &operator=(Completion &&other) noexcept;
    Completion(const Completion &) = delete;
    Completion &operator=(const Completion &) = delete;

    template <typename... Args>
    void Succeed(const Args &...result) {
      Settle(false, [result...]() { return pybind11::make_tuple(result...); });
    }

    void Fail(RTCCallbackException error);

  private:
    void Settle(bool failed, std::function<pybind11::tuple()> args);

    std::shared_ptr<Mailbox> _mailbox;
    uint64_t _token;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_MAILBOX_H_
