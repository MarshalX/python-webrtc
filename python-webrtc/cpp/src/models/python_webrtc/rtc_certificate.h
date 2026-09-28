//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>

#include <rtc_base/rtc_certificate.h>

namespace python_webrtc {

  // A DTLS certificate of a connection (webrtc.RTCCertificate)
  class RTCCertificate {
  public:
    explicit RTCCertificate(webrtc::scoped_refptr<webrtc::RTCCertificate> certificate)
        : _certificate(std::move(certificate)) {}

    static void Init(pybind11::module &m);

    // "rsa", or ECDSA (P-256) for any other key type; null if the key can't be generated
    static std::shared_ptr<RTCCertificate> Generate(
        const std::string &keyType, int modulusLength, int publicExponent, std::optional<uint64_t> expiresMs);

    webrtc::scoped_refptr<webrtc::RTCCertificate> certificate() const { return _certificate; }

    // milliseconds since the epoch
    uint64_t Expires() const { return _certificate->Expires(); }

    // (algorithm, lowercase hex with colons)
    std::vector<std::pair<std::string, std::string>> Fingerprints() const;

  private:
    webrtc::scoped_refptr<webrtc::RTCCertificate> _certificate;
  };

} // namespace python_webrtc
