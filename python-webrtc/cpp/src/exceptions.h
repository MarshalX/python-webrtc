//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

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

  class RTCException : public PythonWebRTCException {
    using PythonWebRTCException::PythonWebRTCException;
  };

  class SdpParseException : public PythonWebRTCException {
    using PythonWebRTCException::PythonWebRTCException;
  };

  class RTCCallbackException : public CallbackPythonWebRTCException {
    using CallbackPythonWebRTCException::CallbackPythonWebRTCException;
  };

  RTCException wrapRTCError(const webrtc::RTCError &error);

  SdpParseException wrapSdpParseError(const webrtc::SdpParseError &error);

  RTCCallbackException wrapRTCErrorForCallback(const webrtc::RTCError &error);

  class Exceptions {
  public:
    static void Init(pybind11::module &m);
  };

} // namespace python_webrtc
