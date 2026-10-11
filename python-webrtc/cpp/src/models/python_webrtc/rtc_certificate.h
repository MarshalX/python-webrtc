//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_CERTIFICATE_H_
#define PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_CERTIFICATE_H_

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>

#include <rtc_base/rtc_certificate.h>

#include "../../utils/native_object.h"

namespace python_webrtc {

  // A DTLS certificate of a connection (webrtc.RTCCertificate)
  class RTCCertificate : public NativeObject<RTCCertificate> {
  public:
    static constexpr const char *kName = "RTCCertificate";

    explicit RTCCertificate(webrtc::scoped_refptr<webrtc::RTCCertificate> certificate)
        : _certificate(std::move(certificate)) {}

    static void Init(pybind11::module &m);

    // "rsa", or ECDSA (P-256) for any other key type; null if the key can't be generated
    static std::shared_ptr<RTCCertificate> Generate(const std::string &keyType, int modulusLength, int publicExponent,
                                                    std::optional<uint64_t> expiresMs);

    [[nodiscard]] webrtc::scoped_refptr<webrtc::RTCCertificate> certificate() const { return _certificate; }

    // milliseconds since the epoch
    [[nodiscard]] uint64_t Expires() const { return _certificate->Expires(); }

    // (algorithm, lowercase hex with colons)
    [[nodiscard]] std::vector<std::pair<std::string, std::string>> Fingerprints() const;

  private:
    webrtc::scoped_refptr<webrtc::RTCCertificate> _certificate;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MODELS_PYTHON_WEBRTC_RTC_CERTIFICATE_H_
