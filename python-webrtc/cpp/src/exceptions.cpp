//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "exceptions.h"

namespace python_webrtc {

  const char *CallbackPythonWebRTCException::what() const noexcept {
    return _msg.c_str();
  }

  [[nodiscard]] const char *PythonWebRTCException::what() const noexcept {
    return _msg.c_str();
  }

  pybind11::object RTCErrorToPython(const webrtc::RTCError &error, std::optional<int> sdpLineNumber) {
    pybind11::object sctpCauseCode = pybind11::none();
    if (error.sctp_cause_code()) {
      sctpCauseCode = pybind11::int_(*error.sctp_cause_code());
    }
    pybind11::object lineNumber = sdpLineNumber ? pybind11::object(pybind11::int_(*sdpLineNumber)) : pybind11::none();
    // the exception classes are defined in Python, to be subclassed and constructed like any Python exception
    return pybind11::module_::import("webrtc.exceptions").attr("_from_native")(
        std::string(ToString(error.type())), std::string(error.message()),
        std::string(ToString(error.error_detail())), sctpCauseCode, lineNumber);
  }

  pybind11::object RTCCallbackException::ToPython() const {
    return RTCErrorToPython(_error, _sdpLineNumber);
  }

  void Exceptions::Init(pybind11::module &m) {
    pybind11::class_<CallbackPythonWebRTCException>(m, "CallbackPythonWebRTCException")
        .def("what", &CallbackPythonWebRTCException::what);
    pybind11::class_<RTCCallbackException, CallbackPythonWebRTCException>(m, "RTCCallbackException")
        .def("to_python", &RTCCallbackException::ToPython);

    static pybind11::exception<PythonWebRTCException> baseExc(m, "PythonWebRTCExceptionBase");

    pybind11::register_exception<PythonWebRTCException>(m, "PythonWebRTCException", baseExc);
    pybind11::register_exception<SdpParseException>(m, "SdpParseException", baseExc);

    // registered last to be tried first
    pybind11::register_exception_translator([](std::exception_ptr p) {
      try {
        if (p) {
          std::rethrow_exception(p);
        }
      } catch (const RTCException &e) {
        auto exc = RTCErrorToPython(e.error());
        PyErr_SetObject(reinterpret_cast<PyObject *>(Py_TYPE(exc.ptr())), exc.ptr());
      }
    });
  }

  RTCException wrapRTCError(const webrtc::RTCError &error) {
    return RTCException(error);
  }

  RTCCallbackException wrapRTCErrorForCallback(const webrtc::RTCError &error) {
    return RTCCallbackException(error);
  }

  SdpParseException wrapSdpParseError(const webrtc::SdpParseError &error) {
    std::string msg;

    if (error.line.empty()) {
      return SdpParseException(msg + error.description);
    } else {
      return SdpParseException(msg + "Line: " + error.line + ".  " + error.description);
    }
  }

} // namespace python_webrtc
