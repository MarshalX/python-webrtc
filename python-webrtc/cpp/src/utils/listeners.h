//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  // Whether Python code can still run: libwebrtc threads may outlive the interpreter
  inline bool PythonAlive() {
#if PY_VERSION_HEX >= 0x030D0000
    return Py_IsInitialized() && !Py_IsFinalizing();
#else
    return Py_IsInitialized() && !_Py_IsFinalizing();
#endif
  }

  // An attribute that changes along with its event, as in a browser, where both change in the same task.
  // While the wrapper has listeners, a change reported by libwebrtc is seen once Python delivers its event
  // (which calls Surface); without listeners there are no events, and the current value is seen.
  template<typename T>
  class Surfaced {
  public:
    // a change reported by libwebrtc, before its event is emitted
    void Changed(bool listening, T previous) {
      std::lock_guard<std::mutex> lock(_mutex);
      if (!listening) {
        _value.reset();
      } else if (!_value) {
        _value = previous;
      }
    }

    void Surface(T value) {
      std::lock_guard<std::mutex> lock(_mutex);
      _value = value;
    }

    // shows the current value again, like when events stop
    void Reset() {
      std::lock_guard<std::mutex> lock(_mutex);
      _value.reset();
    }

    T Get(T current) {
      std::lock_guard<std::mutex> lock(_mutex);
      return _value ? *_value : current;
    }

  private:
    std::mutex _mutex;
    std::optional<T> _value;
  };

  // Event listeners of a wrapper. The Python side (webrtc.utils.events) keeps handlers in a listeners object,
  // which the wrapper holds, so the handlers live as long as the libwebrtc object, not as its Python wrapper.
  //
  // Emit() is called on libwebrtc threads. It takes the GIL and passes the event to the listeners object,
  // which only schedules the handlers on their event loops, so no Python code runs on libwebrtc threads.
  // The listeners object is only touched with the GIL held.
  class Listeners {
  public:
    virtual ~Listeners() {
      DropListeners();
    }

    pybind11::object GetListeners() {
      return _listeners ? _listeners : pybind11::none();
    }

    void SetListeners(pybind11::object listeners) {
      _listeners = listeners.is_none() ? pybind11::object() : std::move(listeners);
      _active = static_cast<bool>(_listeners);
      // events held until Python had the object are delivered now
      if (_active && IsHeld()) {
        Release();
      }
    }

    // whether events are delivered or held for Python
    bool Tracked() {
      return HasListeners() || IsHeld();
    }

    // Adds the listeners property and lets the garbage collector see the handlers, when Python is the only owner
    // of the wrapper, so that handlers referencing the wrapper itself don't keep it alive forever.
    // While libwebrtc (or a parent wrapper) also owns it, the handlers are kept, like listeners in a browser.
    template<typename T, typename... Options>
    static void Bind(pybind11::class_<T, Options...> &cls) {
      cls.def_property("_listeners", &T::GetListeners, &T::SetListeners);
    }

    template<typename T>
    static pybind11::custom_type_setup TypeSetup() {
      return pybind11::custom_type_setup([](PyHeapTypeObject *heap_type) {
        auto *type = &heap_type->ht_type;
        type->tp_flags |= Py_TPFLAGS_HAVE_GC;
        type->tp_traverse = [](PyObject *self, visitproc visit, void *arg) -> int {
          Py_VISIT(Py_TYPE(self));
          if (auto *listeners = OwnedListeners<T>(self)) {
            Py_VISIT(listeners->_listeners.ptr());
          }
          return 0;
        };
        type->tp_clear = [](PyObject *self) -> int {
          if (auto *listeners = OwnedListeners<T>(self)) {
            listeners->_active = false;
            // the handlers may hold the last reference to anything, release them after the field is reset
            pybind11::object dropped = std::move(listeners->_listeners);
          }
          return 0;
        };
      });
    }

    // Events emitted while held are kept, and emitted on release: an object that Python doesn't have yet
    // (like a data channel before its datachannel event) mustn't lose its first events
    void Hold() {
      std::lock_guard<std::mutex> lock(_heldMutex);
      _held = true;
    }

    void Release() {
      std::lock_guard<std::mutex> lock(_heldMutex);
      // emitted under the lock, so that events emitted meanwhile come after these
      for (auto &emit: _heldEvents) {
        emit();
      }
      _heldEvents.clear();
      _held = false;
    }

  protected:
    // Calls the listeners object with the event name and arguments, on any thread
    template<typename... Args>
    void Emit(const char *name, Args... args) {
      {
        std::lock_guard<std::mutex> lock(_heldMutex);
        if (_held) {
          _heldEvents.emplace_back([this, name, args...]() { EmitNow(name, args...); });
          return;
        }
      }
      EmitNow(name, std::move(args)...);
    }

    template<typename... Args>
    void EmitNow(const char *name, Args... args) {
      if (!_active || !PythonAlive()) {
        return;
      }

      pybind11::gil_scoped_acquire gil;
      if (!_listeners) {
        return;
      }
      // keeps the listeners alive even if a handler registration replaces them meanwhile
      pybind11::object listeners = _listeners;
      try {
        listeners(name, std::move(args)...);
      } catch (pybind11::error_already_set &e) {
        e.discard_as_unraisable(name);
      }
    }

    // No events are delivered anymore, and the handlers are released
    void DropListeners() {
      _active = false;
      if (!PythonAlive()) {
        // the interpreter is gone, and so are the objects
        (void) _listeners.release();
        return;
      }
      if (_listeners) {
        pybind11::gil_scoped_acquire gil;
        pybind11::object dropped = std::move(_listeners);
      }
    }

  public:
    bool HasListeners() const {
      return _active;
    }

    // whether events are held, and so are going to be delivered once Python has the object
    bool IsHeld() {
      std::lock_guard<std::mutex> lock(_heldMutex);
      return _held;
    }

    // Stops delivering events without releasing the handlers, e.g. while closing
    void Mute() {
      _active = false;
    }

  private:
    template<typename T>
    static Listeners *OwnedListeners(PyObject *self) {
      auto *inst = reinterpret_cast<pybind11::detail::instance *>(self);
      auto v_h = inst->get_value_and_holder();
      if (!v_h.holder_constructed()) {
        return nullptr;
      }
      auto &holder = v_h.template holder<std::shared_ptr<T>>();
      if (!holder || holder.use_count() != 1) {
        return nullptr;
      }
      return static_cast<Listeners *>(holder.get());
    }

    std::atomic<bool> _active{false};
    pybind11::object _listeners;

    std::mutex _heldMutex;
    bool _held = false;
    std::vector<std::function<void()>> _heldEvents;
  };

} // namespace python_webrtc
