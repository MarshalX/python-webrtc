# Native code

## Threads

libwebrtc has two threads of its own: signaling, and worker (which is also the network thread). Our code runs on
them, and so does Python: events take the GIL there, and the garbage collector can run there and free wrappers.

A deadlock needs a thread that waits for another while holding something the other one needs. So:

### Don't wait while holding a lock

If a libwebrtc thread may take a mutex, lock it with `TrackedLock` and wait with `BlockingCallOn`:

```cpp
const TrackedLock lock(_wrappersMutex);
// ...
BlockingCallOn(_factory->workerThread(), [&]() { /* ... */ });  // aborts: a TrackedLock is held
```

`BlockingCallOn` aborts instead of deadlocking, so the mistake fails the first test that gets there. Always use it
rather than `thread->BlockingCall`.

Beware of waits that don't look like one: libwebrtc proxies (a track's `AddOrUpdateSink`, a connection's
`GetSctpTransport`) call over to their thread and wait too.

### Don't wait while holding the GIL

Bind blocking methods with `nogil()`, or release the GIL with `gil_release` before waiting.

### Constructors and destructors

- Construct wrappers outside locks: `InstanceHolder::GetOrCreate` does, then stores the wrapper under its lock.
- Better, don't wait in a constructor at all: post the setup to its thread instead. Only the ICE, DTLS and SCTP
  transports still wait.
- A destructor that waits must not run on a libwebrtc thread: own the wrapper with `DeleteOffLibwebrtcThread` (or
  through `InstanceHolder`), and start the destructor with `BlockingDestructor`.

### Media threads

Camera, microphone and decoder threads never take the GIL: they hand media to Python through `Wakeup`.

## Ownership

- libwebrtc objects: `webrtc::scoped_refptr`.
- Our wrappers: `std::shared_ptr`. A callback that must not keep one alive holds `weak_from_this()` instead.
- A task posted to another thread that captures `this` goes through `_alive.Guard(...)`, so it does nothing once the
  wrapper is gone. A `BlockingCallOn` capturing `this` is fine: the caller waits for it.
- Raw pointers never own: they point to libwebrtc observers and callbacks, or into C APIs.
- When libwebrtc hands over a raw pointer to own (like `OnSuccess(SessionDescriptionInterface *)`), wrap it in a
  `std::unique_ptr` right away.
- Holders and a few singletons are leaked on purpose (`static auto *holder = new ...`): wrappers can outlive static
  destructors at exit.

## Debugging a hang

Get the stacks of every thread first:

```sh
env -u LD_PRELOAD gdb -p PID -batch -ex "thread apply all bt"   # Linux (gdb breaks under the ASan preload)
lldb -p PID --batch -o "thread backtrace all"                    # macOS
```

Use the `make asan` or `make tsan` build, which has symbols. TSan reports locks taken in opposite orders, but not a
thread waiting for another. A rare race is easier to reproduce by forcing the order (see the tests in
`tests/test_robustness_threads.py`) than by running it in a loop.
