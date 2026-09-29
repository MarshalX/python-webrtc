//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>
#include <utility>

#include <pybind11/pybind11.h>

#include "gil.h"
#include "held_events.h"
#include "libwebrtc_thread.h"

namespace python_webrtc {

  // Event listeners of a wrapper, held here so handlers live as long as the libwebrtc object. Emit() runs on
  // libwebrtc threads: with the GIL, the Python listeners object only schedules handlers on their event loops.
  class Listeners {
  public:
    virtual ~Listeners() {
      DropListeners();
    }

    // the class of a wrapper, with its listeners property
    template<typename T>
    static pybind11::class_<T, std::shared_ptr<T>> BindClass(pybind11::module &m, const char *name) {
      pybind11::class_<T, std::shared_ptr<T>> cls(m, name, TypeSetup<T>());
      cls.def_property("_listeners", &T::GetListeners, &T::SetListeners);
      return cls;
    }

    pybind11::object GetListeners() {
      return _listeners ? _listeners : pybind11::none();
    }

    void SetListeners(pybind11::object listeners) {
      _listeners = listeners.is_none() ? pybind11::object() : std::move(listeners);
      _active = static_cast<bool>(_listeners);
      if (_active) {
        // held events are delivered now, without the GIL: a thread releasing them holds their lock waiting for it
        pybind11::gil_scoped_release release;
        if (IsHeld()) {
          Release();
        }
      }
    }

    bool HasListeners() const {
      return _active;
    }

    // whether events are held, and so are going to be delivered once Python has the object
    bool IsHeld() {
      return _held.IsHeld();
    }

    // whether events are delivered or held for Python
    bool IsTracked() {
      return HasListeners() || IsHeld();
    }

    // Events emitted while held are emitted on release: an object that Python doesn't have yet
    // (like a data channel before its datachannel event) mustn't lose its first events
    void Hold() {
      _held.Hold();
    }

    void Release() {
      _held.Release();
    }

    // Stops delivering events without releasing the handlers, e.g. while closing
    void Mute() {
      _active = false;
    }

  protected:
    // Calls the listeners object with the event name and arguments, on any thread
    template<typename... Args>
    void Emit(const char *name, Args... args) {
      _held.Emit([this, name, args...]() { EmitNow(name, args...); });
    }

    // No events are delivered anymore, and the handlers are released. The destructors of wrappers call it once
    // their libwebrtc objects are released, rather than leaving it to ~Listeners, which runs after the members.
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

  private:
    // Lets the garbage collector see the handlers while Python is the only owner, so handlers referencing
    // the wrapper don't keep it alive forever
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

    template<typename... Args>
    void EmitNow(const char *name, Args... args) {
      if (!_active || !PythonAlive()) {
        return;
      }

      // whatever the handlers release here is destroyed elsewhere
      LibwebrtcThreadScope scope;
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

    std::atomic<bool> _active{false};
    pybind11::object _listeners;
    HeldEvents _held;
  };

} // namespace python_webrtc
