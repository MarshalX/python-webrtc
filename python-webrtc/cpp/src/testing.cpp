//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "testing.h"

#include "exceptions.h"
#include "interfaces/peer_connection_factory.h"
#include "utils/dispatcher.h"
#include "utils/gil.h"
#include "utils/libwebrtc_thread.h"
#include "utils/mailbox.h"
#include "utils/native_object.h"
#include "utils/parking.h"
#include "utils/registry.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <api/make_ref_counted.h>
#include <api/ref_count.h>
#include <api/scoped_refptr.h>

#include <pybind11/stl.h>

namespace python_webrtc {

  namespace {

    struct GuardedTask {
      std::function<void()> run;
      std::shared_ptr<std::atomic<int>> ran;
    };

    class Counted : public NativeObject<Counted> {
    public:
      static constexpr const char *kName = "Counted";

      Counted() = default;

      GuardedTask Guarded() const {
        auto ran = std::make_shared<std::atomic<int>>(0);
        return {.run = Guard([ran]() { (*ran)++; }), .ran = ran};
      }
    };

    class Throwing : public NativeObject<Throwing> {
    public:
      static constexpr const char *kName = "Throwing";

      explicit Throwing(bool fail) {
        if (fail) {
          throw std::invalid_argument("The constructor failed");
        }
      }
    };

    class Identity : public webrtc::RefCountInterface {};

    struct IdentityHandle {
      webrtc::scoped_refptr<Identity> object = webrtc::make_ref_counted<Identity>();
    };

    class Registered : public NativeObject<Registered> {
    public:
      static constexpr const char *kName = "Registered";

      Registered(std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<Identity> identity)
          : _createdOnSignalingThread(factory->signalingThread()->IsCurrent()), _factory(std::move(factory)),
            _identity(std::move(identity)) {}

      static Registry<Registered, Identity> &registry() {
        static ForkLocal<Registry<Registered, Identity>> registry;
        return registry.Get();
      }

      [[nodiscard]] bool CreatedOnSignalingThread() const { return _createdOnSignalingThread; }

    private:
      const bool _createdOnSignalingThread;
      std::shared_ptr<PeerConnectionFactory> _factory;
      webrtc::scoped_refptr<Identity> _identity;
    };

    class Emitting : public NativeObject<Emitting>, public Emitter<Emitting> {
    public:
      static constexpr const char *kName = "Emitting";

      Emitting() = default;

      void EmitValue(int64_t value) { Emit("value", value); }
    };

    struct Unconvertible {};

    // Record::name must outlive the record, like a literal
    const char *Interned(const std::string &name) {
      static auto *names = new std::set<std::string>();
      static auto *mutex = new std::mutex();
      const std::scoped_lock lock(*mutex);
      return names->insert(name).first->c_str();
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): mirrors post_from_threads(mailbox, threads, count)
    void PostFromThreads(Mailbox &mailbox, int threads, int count) {
      std::vector<std::thread> posting;
      posting.reserve(threads);
      for (int thread = 0; thread < threads; thread++) {
        posting.emplace_back([&mailbox, thread, count]() {
          for (int i = 0; i < count; i++) {
            mailbox.Post(Record{.name = "posted", .args = [thread, i]() { return pybind11::make_tuple(thread, i); }});
          }
        });
      }
      for (auto &thread : posting) {
        thread.join();
      }
    }

  } // namespace

  void Testing::Init(pybind11::module &m) {
    auto testing = m.def_submodule("_testing", "Hooks into the native threads and primitives, for the tests");

    testing.def("dispatcher_threads", &Dispatcher::Threads,
                "The Dispatcher threads started by this process: at most one.");
    testing.def("dispatcher_idle", &Dispatcher::Idle, nogil(),
                "Blocks until the Dispatcher has nothing queued nor running; returns at once if it never started.");
    testing.def("park", &Parking::Park, pybind11::arg("name"),
                "Holds a parking point: the next native thread reaching it blocks until release(name).");
    testing.def("release", &Parking::Release, pybind11::arg("name"), "Lets the threads parked at a point go on.");
    testing.def("parked", &Parking::Parked, nogil(), pybind11::arg("name"), pybind11::arg("timeout"),
                "Whether a thread is parked at a point, waiting up to the timeout (in seconds) for one.");
    testing.def("alive_counts", &AliveCounts, nogil(),
                "The objects alive of every NativeObject type by its name, in key order, zeros included.");

    pybind11::class_<GuardedTask>(testing, "GuardedTask", "A task guarded by the life of the object that made it.")
        .def("__call__", [](const GuardedTask &task) { task.run(); })
        .def_property_readonly(
            "ran", [](const GuardedTask &task) { return task.ran->load(); }, "How many times the task ran.");
    pybind11::class_<Counted, std::shared_ptr<Counted>>(testing, "Counted",
                                                        "A NativeObject counted under 'Counted', made by Create.")
        .def(pybind11::init([]() { return Counted::Create(); }))
        .def_property_readonly("id", &Counted::Id, "The id of the object, never reused.")
        .def("guarded", &Counted::Guarded, "A task that counts its runs while the object is alive.");
    testing.def(
        "check_destroyed_off_dispatcher", []() { delete new Counted(); },
        "Destroys a NativeObject on the calling thread, which sanitizer builds abort on.");
    testing.def(
        "check_blocking_while_attached",
        []() {
          std::shared_ptr<PeerConnectionFactory> factory;
          {
            const gil_release release;
            factory = PeerConnectionFactory::GetOrCreateDefault();
          }
          BlockingCallOn(factory->signalingThread(), []() {});
        },
        "Blocks on a libwebrtc thread with the GIL held, which sanitizer builds abort on.");
    pybind11::class_<Throwing, std::shared_ptr<Throwing>>(testing, "Throwing",
                                                          "A NativeObject counted under 'Throwing', made by Create.")
        .def(pybind11::init(nogil_factory(+[](bool fail) { return Throwing::Create(fail); })), pybind11::arg("fail"),
             "Raises ValueError from the constructor when fail is set.");

    pybind11::class_<Emitting, std::shared_ptr<Emitting>>(testing, "Emitting",
                                                          "A NativeObject with a 'value' event, bound to a mailbox.")
        .def(pybind11::init([]() { return Emitting::Create(); }))
        .def_property_readonly("id", &Emitting::Id, "The id of the object, never reused.")
        .def("bind", &Emitting::Bind, nogil(), pybind11::arg("mailbox"),
             "Binds the object to a mailbox: the first binding wins, until its mailbox is closed.")
        .def(
            "inherit", [](Emitting &self, const Emitting &parent) { self.Inherit(parent); }, nogil(),
            pybind11::arg("parent"), "Takes the binding of a parent.")
        .def("unbind", &Emitting::Unbind, nogil(), "Drops the binding.")
        .def_property_readonly("bound", &Emitting::IsBound, "Whether bound to a mailbox that isn't closed.")
        .def("emit", &Emitting::EmitValue, nogil(), pybind11::arg("value"),
             "Posts a 'value' event whose args are (self, value), or nothing when unbound.");
    pybind11::class_<IdentityHandle>(testing, "Identity", "A libwebrtc-like object with an identity.")
        .def(pybind11::init<>());
    pybind11::class_<Registered, std::shared_ptr<Registered>>(testing, "Registered",
                                                              "The wrapper of an Identity, made by a Registry.")
        .def_property_readonly("id", &Registered::Id, "The id of the object, never reused.")
        .def_property_readonly("createdOnSignalingThread", &Registered::CreatedOnSignalingThread,
                               "Whether the constructor ran on the signaling thread of the default factory.");
    testing.def(
        "registered",
        [](const IdentityHandle &identity) {
          return Registered::registry().GetOrCreate(PeerConnectionFactory::GetOrCreateDefault(), identity.object);
        },
        nogil(), pybind11::arg("identity"), "The Registered wrapper of an identity, created on first use.");
    testing.def(
        "find_registered",
        [](const IdentityHandle &identity) { return Registered::registry().Find(identity.object.get()); }, nogil(),
        pybind11::arg("identity"), "The live Registered wrapper of an identity, or None.");

    testing.def(
        "post",
        [](Mailbox &mailbox, const std::string &name, int64_t value) {
          mailbox.Post(Record{.name = Interned(name), .args = [value]() { return pybind11::make_tuple(value); }});
        },
        nogil(), pybind11::arg("mailbox"), pybind11::arg("name"), pybind11::arg("value"),
        "Posts an event record without a target, whose args are (value,).");
    testing.def("post_from_threads", &PostFromThreads, nogil(), pybind11::arg("mailbox"), pybind11::arg("threads"),
                pybind11::arg("count"),
                "Starts native threads that each post count 'posted' records with args (thread, i), and joins them.");
    testing.def(
        "post_unconvertible",
        [](Mailbox &mailbox) {
          mailbox.Post(Record{.name = "unconvertible", .args = []() { return pybind11::make_tuple(Unconvertible{}); }});
        },
        nogil(), pybind11::arg("mailbox"), "Posts a record whose args don't convert to Python.");
    testing.def(
        "complete",
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): mirrors complete(mailbox, token, value)
        [](std::shared_ptr<Mailbox> mailbox, uint64_t token, int64_t value) {
          Completion completion(std::move(mailbox), token);
          completion.Succeed(value);
        },
        nogil(), pybind11::arg("mailbox"), pybind11::arg("token"), pybind11::arg("value"),
        "Settles a completion of the token with the value.");
    testing.def(
        "fail",
        [](std::shared_ptr<Mailbox> mailbox, uint64_t token) {
          Completion completion(std::move(mailbox), token);
          completion.Fail(RTCCallbackException(webrtc::RTCErrorType::INTERNAL_ERROR, "The operation failed"));
        },
        nogil(), pybind11::arg("mailbox"), pybind11::arg("token"), "Fails a completion of the token.");
    testing.def(
        "abandon",
        [](std::shared_ptr<Mailbox> mailbox, uint64_t token) {
          std::thread([mailbox = std::move(mailbox), token]() { const Completion completion(mailbox, token); }).join();
        },
        nogil(), pybind11::arg("mailbox"), pybind11::arg("token"),
        "Destroys an unsettled completion of the token on a native thread.");
  }

} // namespace python_webrtc
