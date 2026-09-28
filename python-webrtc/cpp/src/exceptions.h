//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <optional>

#include <pybind11/pybind11.h>

#include <api/rtc_error.h>
#include <api/jsep.h>

namespace python_webrtc {

  class CallbackPythonWebRTCException {
  public:
    explicit CallbackPythonWebRTCException(std::string msg) : _msg(std::move(msg)) {}

    [[nodiscard]] const char *what() const noexcept;

  private:
    std::string _msg;
  };

  class PythonWebRTCException : public std::exception {
  public:
    explicit PythonWebRTCException(std::string msg) : _msg(std::move(msg)) {}

    [[nodiscard]] const char *what() const noexcept override;

  private:
    std::string _msg;
  };

  // An error of libwebrtc. Raised in Python as the subclass of webrtc.RTCException for its type
  // (see webrtc/exceptions.py), the way browsers turn webrtc::RTCError into DOM exceptions.
  class RTCException : public PythonWebRTCException {
  public:
    explicit RTCException(webrtc::RTCError error)
        : PythonWebRTCException(error.message()), _error(std::move(error)) {}

    RTCException(webrtc::RTCErrorType type, std::string msg)
        : PythonWebRTCException(msg), _error(type, msg) {}

    [[nodiscard]] const webrtc::RTCError &error() const { return _error; }

  private:
    webrtc::RTCError _error;
  };

  class SdpParseException : public PythonWebRTCException {
    using PythonWebRTCException::PythonWebRTCException;
  };

  // An RTCException passed to a Python callback of an asynchronous operation instead of being raised
  class RTCCallbackException : public CallbackPythonWebRTCException {
  public:
    explicit RTCCallbackException(webrtc::RTCError error, std::optional<int> sdpLineNumber = std::nullopt)
        : CallbackPythonWebRTCException(error.message()), _error(std::move(error)), _sdpLineNumber(sdpLineNumber) {}

    RTCCallbackException(webrtc::RTCErrorType type, std::string msg)
        : CallbackPythonWebRTCException(msg), _error(type, msg) {}

    [[nodiscard]] const webrtc::RTCError &error() const { return _error; }

    // the Python exception (a webrtc.RTCException subclass) for the error
    [[nodiscard]] pybind11::object ToPython() const;

  private:
    webrtc::RTCError _error;
    std::optional<int> _sdpLineNumber;
  };

  RTCException wrapRTCError(const webrtc::RTCError &error);

  SdpParseException wrapSdpParseError(const webrtc::SdpParseError &error);

  RTCCallbackException wrapRTCErrorForCallback(const webrtc::RTCError &error);

  // the Python exception (a webrtc.RTCException subclass) for a libwebrtc error
  pybind11::object RTCErrorToPython(const webrtc::RTCError &error, std::optional<int> sdpLineNumber = std::nullopt);

  class Exceptions {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc
