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

  void Exceptions::Init(pybind11::module &m) {
    pybind11::class_<CallbackPythonWebRTCException>(m, "CallbackPythonWebRTCException")
        .def("what", &CallbackPythonWebRTCException::what);
    pybind11::class_<RTCCallbackException>(m, "RTCCallbackException")
        .def("what", &RTCCallbackException::what);

    static pybind11::exception<PythonWebRTCException> baseExc(m, "PythonWebRTCExceptionBase");

    pybind11::register_exception<PythonWebRTCException>(m, "PythonWebRTCException", baseExc);
    pybind11::register_exception<RTCException>(m, "RTCException", baseExc);
    pybind11::register_exception<SdpParseException>(m, "SdpParseException", baseExc);
  }

  RTCException wrapRTCError(const webrtc::RTCError &error) {
    std::string msg;
    return RTCException(msg + "[" + ToString(error.type()) + "] " + error.message());
  }

  RTCCallbackException wrapRTCErrorForCallback(const webrtc::RTCError &error) {
    std::string msg;
    return RTCCallbackException(msg + "[" + ToString(error.type()) + "] " + error.message());
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
