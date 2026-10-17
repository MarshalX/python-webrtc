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
    ~Mailbox();

    Mailbox(const Mailbox &) = delete;
    Mailbox &operator=(const Mailbox &) = delete;

    [[nodiscard]] uint64_t Id() const { return _id; }

    struct WakeEnds {
      int read;
      int write;
    };

    std::optional<int> EnableWake();

    bool AckWake();

    void DisableWake();

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
    [[nodiscard]] const WakeEnds *WakeLocked() const;
    void CloseWakeLocked();

    const uint64_t _id;
    mutable std::mutex _mutex;
    std::deque<Record> _records;
    bool _awake = false;
    bool _closed = false;
    uint64_t _dropped = 0;
    std::optional<WakeEnds> _wake;
    int _wakeForks = 0;
  };

  class Binding {
  public:
    // the first binding wins until its mailbox closes
    bool Bind(std::shared_ptr<Mailbox> mailbox);

    void Inherit(const Binding &parent);

    // the id of the mailbox it was bound to, if any
    std::optional<uint64_t> Unbind();

    [[nodiscard]] bool IsBound() const;

    [[nodiscard]] bool IsOrphaned() const;

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
        .def_property_readonly("_orphaned", [](const T &self) { return self.IsOrphaned(); })
        .def_property_readonly("_mailbox", [](const T &self) { return self.MailboxId(); });
    return cls;
  }

  template <typename T>
  class Emitter : public Binding {
  protected:
    // an rvalue argument is moved into the record, and from it into Python
    template <typename... Args>
    void Emit(const char *name, Args &&...args) {
      auto self = Source();
      if (!self) {
        return;
      }
      // Take converts a record once
      Post(Record{.source = self,
                  .target = self->Id(),
                  .name = name,
                  // NOLINTNEXTLINE(clang-analyzer-cplusplus.NewDeleteLeaks): the analyzer loses a moved shared_ptr
                  .args = [self, ... args = std::forward<Args>(args)]() mutable {
                    return pybind11::make_tuple(self, std::move(args)...);
                  }});
    }

    template <typename Convert>
    void EmitConverted(const char *name, Convert convert) {
      auto self = Source();
      if (!self) {
        return;
      }
      Post(Record{.source = self,
                  .target = self->Id(),
                  .name = name,
                  // NOLINTNEXTLINE(clang-analyzer-cplusplus.NewDeleteLeaks): the analyzer loses a moved shared_ptr
                  .args = [self, convert = std::move(convert)]() { return pybind11::make_tuple(self, convert()); }});
    }

  private:
    std::shared_ptr<T> Source() {
      CheckNativeThreadDetached("Emitter::Emit");
      if (!IsBound()) {
        return nullptr;
      }
      // nothing keeps it for the record while its constructor runs
      return static_cast<T *>(this)->weak_from_this().lock();
    }

    friend T;

    Emitter() = default;
  };

  class Completion {
  public:
    Completion(std::shared_ptr<Mailbox> mailbox, uint64_t token);

    ~Completion();

    Completion(Completion &&other) noexcept;
    Completion &operator=(Completion &&other) = delete;
    Completion(const Completion &) = delete;
    Completion &operator=(const Completion &) = delete;

    template <typename... Args>
    void Succeed(const Args &...result) {
      Settle(false, [result...]() { return pybind11::make_tuple(result...); });
    }

    template <typename Convert>
    void SucceedWith(Convert convert) {
      Settle(false, [convert = std::move(convert)]() { return pybind11::make_tuple(convert()); });
    }

    void Fail(RTCCallbackException error);

  private:
    void Settle(bool failed, std::function<pybind11::tuple()> args);

    std::shared_ptr<Mailbox> _mailbox;
    uint64_t _token;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_MAILBOX_H_
