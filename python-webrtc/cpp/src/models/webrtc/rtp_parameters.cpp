//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtp_parameters.h"

#include <pybind11/stl.h>

#include <api/priority.h>
#include <api/rtp_parameters.h>

namespace python_webrtc {

  void bindRtpParameters(pybind11::module &m) {
    pybind11::class_<webrtc::RtpCodec>(m, "RtpCodec")
        .def(pybind11::init<>())
        .def_readwrite("name", &webrtc::RtpCodec::name)
        .def_readwrite("kind", &webrtc::RtpCodec::kind)
        .def_readwrite("clockRate", &webrtc::RtpCodec::clock_rate)
        .def_readwrite("numChannels", &webrtc::RtpCodec::num_channels)
        .def_property("parameters",
                      [](const webrtc::RtpCodec &codec) {
                        return std::map<std::string, std::string>(codec.parameters.begin(), codec.parameters.end());
                      },
                      [](webrtc::RtpCodec &codec, const std::map<std::string, std::string> &parameters) {
                        codec.parameters = webrtc::CodecParameterMap(parameters);
                      })
        .def_property_readonly("mimeType", &webrtc::RtpCodec::mime_type);

    pybind11::class_<webrtc::RtpCodecCapability, webrtc::RtpCodec>(m, "RtpCodecCapability")
        .def(pybind11::init<>())
        .def_readwrite("preferredPayloadType", &webrtc::RtpCodecCapability::preferred_payload_type);

    pybind11::class_<webrtc::RtpCodecParameters, webrtc::RtpCodec>(m, "RtpCodecParameters")
        .def(pybind11::init<>())
        .def_readwrite("payloadType", &webrtc::RtpCodecParameters::payload_type);

    pybind11::class_<webrtc::RtpExtension>(m, "RtpExtension")
        .def(pybind11::init<>())
        .def_readwrite("uri", &webrtc::RtpExtension::uri)
        .def_property("id",
                      [](const webrtc::RtpExtension &extension) { return extension.id.value(); },
                      [](webrtc::RtpExtension &extension, int id) { extension.id = webrtc::RtpHeaderExtensionId(id); })
        .def_readwrite("encrypt", &webrtc::RtpExtension::encrypt);

    pybind11::class_<webrtc::RtpHeaderExtensionCapability>(m, "RtpHeaderExtensionCapability")
        .def(pybind11::init<>())
        .def_readwrite("uri", &webrtc::RtpHeaderExtensionCapability::uri)
        .def_property("preferredId",
                      [](const webrtc::RtpHeaderExtensionCapability &capability) -> std::optional<int> {
                        if (!capability.preferred_id) {
                          return std::nullopt;
                        }
                        return capability.preferred_id->value();
                      },
                      [](webrtc::RtpHeaderExtensionCapability &capability, std::optional<int> id) {
                        if (id) {
                          capability.preferred_id = webrtc::RtpHeaderExtensionId(*id);
                        } else {
                          capability.preferred_id.reset();
                        }
                      })
        .def_readwrite("direction", &webrtc::RtpHeaderExtensionCapability::direction);

    pybind11::class_<webrtc::RtcpParameters>(m, "RtcpParameters")
        .def(pybind11::init<>())
        .def_readwrite("cname", &webrtc::RtcpParameters::cname)
        .def_readwrite("reducedSize", &webrtc::RtcpParameters::reduced_size);

    pybind11::class_<webrtc::RtpEncodingParameters>(m, "RtpEncodingParameters")
        .def(pybind11::init<>())
        .def_readwrite("active", &webrtc::RtpEncodingParameters::active)
        .def_readwrite("requestKeyFrame", &webrtc::RtpEncodingParameters::request_key_frame)
        .def_readwrite("maxBitrate", &webrtc::RtpEncodingParameters::max_bitrate_bps)
        .def_readwrite("maxFramerate", &webrtc::RtpEncodingParameters::max_framerate)
        .def_readwrite("rid", &webrtc::RtpEncodingParameters::rid)
        .def_readwrite("scaleResolutionDownBy", &webrtc::RtpEncodingParameters::scale_resolution_down_by)
        .def_readwrite("scalabilityMode", &webrtc::RtpEncodingParameters::scalability_mode)
        .def_readwrite("bitratePriority", &webrtc::RtpEncodingParameters::bitrate_priority)
        .def_readwrite("networkPriority", &webrtc::RtpEncodingParameters::network_priority)
        .def_readwrite("adaptivePtime", &webrtc::RtpEncodingParameters::adaptive_ptime)
        .def_readwrite("codec", &webrtc::RtpEncodingParameters::codec)
        .def_readwrite("ssrc", &webrtc::RtpEncodingParameters::ssrc);

    pybind11::class_<webrtc::RtpParameters>(m, "RtpParameters")
        .def(pybind11::init<>())
        .def_readwrite("transactionId", &webrtc::RtpParameters::transaction_id)
        .def_readwrite("mid", &webrtc::RtpParameters::mid)
        .def_readwrite("codecs", &webrtc::RtpParameters::codecs)
        .def_readwrite("headerExtensions", &webrtc::RtpParameters::header_extensions)
        .def_readwrite("encodings", &webrtc::RtpParameters::encodings)
        .def_readwrite("rtcp", &webrtc::RtpParameters::rtcp)
        .def_readwrite("degradationPreference", &webrtc::RtpParameters::degradation_preference);

    pybind11::class_<webrtc::RtpCapabilities>(m, "RtpCapabilities")
        .def(pybind11::init<>())
        .def_readwrite("codecs", &webrtc::RtpCapabilities::codecs)
        .def_readwrite("headerExtensions", &webrtc::RtpCapabilities::header_extensions);
  }

} // namespace python_webrtc
