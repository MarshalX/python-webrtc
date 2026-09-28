//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_certificate.h"

#include <algorithm>
#include <cctype>

#include <pybind11/stl.h>

#include <rtc_base/rtc_certificate_generator.h>
#include <rtc_base/ssl_fingerprint.h>

#include "../../utils/gil.h"

namespace python_webrtc {

  void Certificate::Init(pybind11::module &m) {
    pybind11::class_<Certificate, std::shared_ptr<Certificate>>(m, "RTCCertificate")
        .def_static("generate", &Certificate::Generate, nogil())
        .def_property_readonly("expires", &Certificate::Expires)
        .def("fingerprints", &Certificate::Fingerprints);
  }

  std::shared_ptr<Certificate> Certificate::Generate(
      const std::string &keyType, int modulusLength, int publicExponent, std::optional<uint64_t> expiresMs) {
    auto params = keyType == "rsa" ? webrtc::KeyParams::RSA(modulusLength, publicExponent) : webrtc::KeyParams::ECDSA();
    if (!params.IsValid()) {
      return nullptr;
    }
    auto certificate = webrtc::RTCCertificateGenerator::GenerateCertificate(params, expiresMs);
    return certificate ? std::make_shared<Certificate>(certificate) : nullptr;
  }

  std::vector<std::pair<std::string, std::string>> Certificate::Fingerprints() const {
    std::vector<std::pair<std::string, std::string>> fingerprints;
    auto fingerprint = webrtc::SSLFingerprint::CreateFromCertificate(*_certificate);
    if (fingerprint) {
      auto value = fingerprint->GetRfc4572Fingerprint();
      std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return std::tolower(c); });
      fingerprints.emplace_back(fingerprint->algorithm, value);
    }
    return fingerprints;
  }

} // namespace python_webrtc
