//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "exceptions.h"
#include "enums/enums.h"

namespace python_webrtc {

  [[nodiscard]] const char *PythonWebRTCException::what() const noexcept {
    return _msg.c_str();
  }

  webrtc::RTCError closedError(const std::string &method, const std::string &interface) {
    return {webrtc::RTCErrorType::INVALID_STATE, "Failed to execute '" + method + "' on '" + interface +
                                                     "': The RTCPeerConnection's signalingState is 'closed'."};
  }

  pybind11::object rtcErrorToPython(const webrtc::RTCError &error, std::optional<int> sdpLineNumber) {
    pybind11::object sctpCauseCode = pybind11::none();
    if (error.sctp_cause_code()) {
      sctpCauseCode = pybind11::int_(*error.sctp_cause_code());
    }
    const pybind11::object lineNumber =
        sdpLineNumber ? pybind11::object(pybind11::int_(*sdpLineNumber)) : pybind11::none();
    pybind11::object detail = pybind11::none();
    if (error.error_detail() != webrtc::RTCErrorDetailType::NONE) {
      detail = pybind11::cast(error.error_detail());
    }
    // the exception classes are defined in Python, to be subclassed and constructed like any Python exception
    return pybind11::module_::import("webrtc.exceptions")
        .attr("_from_native")(std::string(ToString(error.type())), std::string(error.message()), detail, sctpCauseCode,
                              lineNumber);
  }

  pybind11::object RTCCallbackException::ToPython() const {
    return rtcErrorToPython(_error, _sdpLineNumber);
  }

  void Exceptions::Init(pybind11::module &m) {
    pybind11::class_<RTCCallbackException>(m, "RTCCallbackException").def("toPython", &RTCCallbackException::ToPython);

    static const pybind11::exception<PythonWebRTCException> baseExc(m, "PythonWebRTCExceptionBase");

    pybind11::register_exception<PythonWebRTCException>(m, "PythonWebRTCException", baseExc);
    pybind11::register_exception<SdpParseException>(m, "SdpParseException", baseExc);

    // registered last to be tried first; pybind11's translator type takes the pointer by value
    // NOLINTNEXTLINE(performance-unnecessary-value-param)
    pybind11::register_exception_translator([](std::exception_ptr error) {
      try {
        if (error) {
          std::rethrow_exception(error);
        }
      } catch (const RTCException &e) {
        auto exc = rtcErrorToPython(e.error());
        PyErr_SetObject(exc.get_type().ptr(), exc.ptr());
      }
    });
  }

} // namespace python_webrtc
