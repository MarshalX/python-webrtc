//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_EXCEPTIONS_H_
#define PYTHON_WEBRTC_EXCEPTIONS_H_

#include <optional>
#include <string>

#include <api/rtc_error.h>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class PythonWebRTCException : public std::exception {
  public:
    explicit PythonWebRTCException(std::string msg) : _msg(std::move(msg)) {}

    [[nodiscard]] const char *what() const noexcept override;

  private:
    std::string _msg;
  };

  // An error of libwebrtc. Raised in Python as the subclass of webrtc.RTCException for its type
  // (see webrtc/exceptions.py).
  class RTCException : public PythonWebRTCException {
  public:
    explicit RTCException(webrtc::RTCError error) : PythonWebRTCException(error.message()), _error(std::move(error)) {}

    RTCException(webrtc::RTCErrorType type, const std::string &msg) : PythonWebRTCException(msg), _error(type, msg) {}

    [[nodiscard]] const webrtc::RTCError &error() const { return _error; }

  private:
    webrtc::RTCError _error;
  };

  // An RTCException passed to a Python callback of an asynchronous operation instead of being raised
  class RTCCallbackException {
  public:
    explicit RTCCallbackException(webrtc::RTCError error, std::optional<int> sdpLineNumber = std::nullopt)
        : _error(std::move(error)), _sdpLineNumber(sdpLineNumber) {}

    RTCCallbackException(webrtc::RTCErrorType type, const std::string &msg) : _error(type, msg) {}

    [[nodiscard]] const webrtc::RTCError &error() const { return _error; }

    // the Python exception (a webrtc.RTCException subclass) for the error
    [[nodiscard]] pybind11::object ToPython() const;

  private:
    webrtc::RTCError _error;
    std::optional<int> _sdpLineNumber;
  };

  // The error of a method called on a closed connection, or on an object of one
  webrtc::RTCError closedError(const std::string &method, const std::string &interface = "RTCPeerConnection");

  // the Python exception (a webrtc.RTCException subclass) for a libwebrtc error
  pybind11::object rtcErrorToPython(const webrtc::RTCError &error, std::optional<int> sdpLineNumber = std::nullopt);

  class Exceptions {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_EXCEPTIONS_H_
