# Native code

## Threads

Native threads never run Python. libwebrtc's signaling and worker threads, and the media threads (capture, decoders,
the audio device, frame transformers), only post records to the mailbox of an event loop. One thread, the
Dispatcher, enters Python, only to wake a loop, which then converts the records and runs the handlers. Python code
and the garbage collector therefore only run on Python threads.

The extension doesn't need the GIL (`mod_gil_not_used`): on a free-threaded build, Python threads call one wrapper
at once, so every member a bound method touches is immutable after construction, atomic, or guarded by the
wrapper's mutex; what wraps on the signaling thread (`Registry`, a connection's `Wrap`) is serialized there.

A deadlock needs a thread that waits for another while holding something the other one needs. So:

### Don't wait while holding a lock

If a libwebrtc thread may take a mutex, lock it with `TrackedLock` and wait with `BlockingCallOn`:

```cpp
const TrackedLock lock(_wrappersMutex);
BlockingCallOn(_factory->workerThread(), [&]() { /* ... */ });  // aborts: a TrackedLock is held
```

`BlockingCallOn` aborts instead of deadlocking, so the mistake fails the first test that gets there. Always use it
rather than `thread->BlockingCall`. Beware of waits that don't look like one: libwebrtc proxies (a track's
`AddOrUpdateSink`, a connection's `GetSctpTransport`) call over to their thread and wait too.

### Detach from Python while waiting

Bind blocking methods with `nogil()`, or detach with `gil_release` before waiting. No native thread needs Python, so
this isn't about deadlocks: an attached thread that waits holds up the other Python threads and, on free-threaded
builds, the garbage collector's stop-the-world pause.

Sanitizer builds abort on a `BlockingCallOn` from an attached thread, and on a libwebrtc or media thread that is
attached when it posts (`utils/libwebrtc_thread.h`). `tests/test_native_rules.py` checks the rules a grep can.

### Constructors and destructors

- Create wrappers with `NativeObject<T>::Create` or a `Registry`. Construct them outside locks.
- Don't wait in a constructor: post the setup to its thread instead.
- Destructors run on the Dispatcher, never on a libwebrtc or Python thread, so they may wait for libwebrtc threads.

A `Registry` constructs its wrappers on the signaling thread, where their observers are registered. Sanitizer builds
abort on a destructor that runs off the Dispatcher; a constructor that throws is the exception: the half-made object
is destroyed where it was made. The factory and the ICE, DTLS and SCTP transports still wait in their constructors.

### The Dispatcher and mailboxes

- `Dispatcher` (`utils/dispatcher.h`): one detached thread, the only native thread that enters Python, and only to
  wake a loop (`webrtc.utils.loops._wake`). Before 3.15 it takes the GIL; from 3.15 it uses PEP 788. It also runs
  the destructors handed to `Destroy`, one at a time, detached.
- At exit, `StopAtExit` blocks new entries (waits, bounded, for one in progress) and leaks queued destructors.
  Before 3.14, a detached thread that would take the GIL back waits for the process to end instead (`gil_release`).
- After a fork, the child restarts the thread, leaks the parent's queued work, never destroys pre-fork objects
  (`Destroy` takes a generation) and remakes the registries (`ForkLocal`), which a parent thread may have held locked.
- `Mailbox` (`utils/mailbox.h`): one event loop's record queue. Native threads post events, completions and markers
  under its leaf mutex; a post into an empty mailbox wakes the loop. The loop takes records in order and converts
  them there. Closing drops queued and later records.
- A method that completes later (`createOffer`, `getStats`...) takes `(mailbox, token)` from `loops.call_native`
  and wraps them in a `Completion` first thing. It's settled once with `Succeed(...)` or `Fail`; destroyed unsettled
  (e.g. a callback libwebrtc drops), it fails with `InvalidStateError`. At exit, `loops._exit` cancels calls in
  flight before the Dispatcher stops.
- Classes with events derive from `Emitter<T>`: `Emit(name, args...)` copies native args into a record for the
  object's `Binding`, or does nothing while unbound. Python binds an object when it wraps it on a running loop; the
  first binding holds until that loop is released. Children the connection creates natively inherit its binding, so
  their records queue behind the parent's event. Closing a connection unbinds its children (`Surfaced` reads
  `IsBound()`). `HeldEvents` only orders events inside libwebrtc callbacks.
- `DefineBinding(cls)` defines `_bind`, `_bound` and `_mailbox` per class, not on a pybind base: a base method costs
  a derived-to-base cast per call (6–8 µs vs 0.1 µs).
- `NativeObject<T>` (`utils/native_object.h`) counts objects per `T::kName` (`AliveCounts()`) and exposes `_id`,
  which `webrtc.utils.lifetime` keys one Python wrapper on. A `Registry` (`utils/registry.h`) keeps one wrapper per
  libwebrtc object. `wrtc._testing` exposes these plus parking points (`utils/parking.h`) that stop a native thread
  where a test needs it.

## Ownership

One direction: Python → C++ → libwebrtc.

- C++ never holds a Python object: no `pybind11::object`, `function` or `handle` member or capture. Python state
  lives on the Python wrapper; native state that Python sets is converted to native values. (The only exception is
  the Dispatcher's wake function.) `tests/test_native_rules.py` checks it.
- libwebrtc objects: `webrtc::scoped_refptr`. Our wrappers: `std::shared_ptr`, created by `NativeObject::Create`,
  which destroys them on the Dispatcher.
- Parents hold children; children hold their parent weakly (`weak_from_this()`). Shared services (the factory, the
  Dispatcher, mailboxes) are held strongly and hold no wrappers. A mailbox's records keep their source until drained
  or dropped, the only allowed cycle.
- A task posted to another thread that captures `this` goes through `Guard(...)`, so it does nothing once the
  wrapper is gone. A `BlockingCallOn` capturing `this` is fine: the caller waits for it. A callback that can't be
  unregistered is ended by `Disarm()` at the start of the destructor, which then waits for the callback's thread once.
- Raw pointers never own: they point to libwebrtc observers and callbacks, or into C APIs. A raw pointer libwebrtc
  hands over to own (`OnSuccess(SessionDescriptionInterface *)`) goes into a `std::unique_ptr` right away.
- An event's arguments are native values copied at `Emit`; they're converted to Python on the loop thread.
- Registries and the Dispatcher are leaked on purpose (`static auto *x = new ...`, `ForkLocal`): native threads can
  outlive static destructors at exit.

## Lifetime

Python decides what an unreferenced object's lifetime is, per event loop (`webrtc/utils/loops.py`): an object stays
alive while it can still fire an event that has a handler, following the WebRTC specifications (each class's
`_activity()`). A closed or collected loop releases everything it kept: its mailbox closes, pending operations are
cancelled, and its handlers are removed. Everything else is plain Python garbage.

## Debugging a hang

Get the stacks of every thread first: `make stacks PID=...` (`O=--signal` adds the Python stacks on the process's
stderr); `make hunt` does this on every hang, see `scripts/debug/README.md`. By hand on Linux, gdb breaks under the
ASan preload: `env -u LD_PRELOAD gdb -p PID -batch -ex "thread apply all bt"`.

Use the `make asan` or `make tsan` build, which has symbols. TSan reports locks taken in opposite orders, but not a
thread waiting for another. A rare race is easier to reproduce by forcing the order (see the tests in
`tests/test_robustness_threads.py`) than by running it in a loop.
