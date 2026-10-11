//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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

  void RTCCertificate::Init(pybind11::module &m) {
    pybind11::class_<RTCCertificate, std::shared_ptr<RTCCertificate>>(m, "RTCCertificate")
        .def_property_readonly("_id", &RTCCertificate::Id)
        .def_static("generate", &RTCCertificate::Generate, nogil(), pybind11::arg("keyType"),
                    pybind11::arg("modulusLength"), pybind11::arg("publicExponent"), pybind11::arg("expires"))
        .def_property_readonly("expires", &RTCCertificate::Expires)
        .def("fingerprints", &RTCCertificate::Fingerprints);
  }

  std::shared_ptr<RTCCertificate> RTCCertificate::Generate(const std::string &keyType, int modulusLength,
                                                           int publicExponent, std::optional<uint64_t> expiresMs) {
    auto params = keyType == "rsa" ? webrtc::KeyParams::RSA(modulusLength, publicExponent) : webrtc::KeyParams::ECDSA();
    if (!params.IsValid()) {
      return nullptr;
    }
    auto certificate = webrtc::RTCCertificateGenerator::GenerateCertificate(params, expiresMs);
    return certificate ? Create(certificate) : nullptr;
  }

  std::vector<std::pair<std::string, std::string>> RTCCertificate::Fingerprints() const {
    std::vector<std::pair<std::string, std::string>> fingerprints;
    auto fingerprint = webrtc::SSLFingerprint::CreateFromCertificate(*_certificate);
    if (fingerprint) {
      auto value = fingerprint->GetRfc4572Fingerprint();
      std::ranges::transform(value, value.begin(), [](unsigned char character) { return std::tolower(character); });
      fingerprints.emplace_back(fingerprint->algorithm, value);
    }
    return fingerprints;
  }

} // namespace python_webrtc
