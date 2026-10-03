//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_transceiver.h"

#include "../exceptions.h"
#include "../utils/gil.h"
#include "rtc_peer_connection.h"

namespace python_webrtc {

  RTCRtpTransceiver::RTCRtpTransceiver(std::shared_ptr<PeerConnectionFactory> factory,
                                       webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver)
      : _factory(std::move(factory)), _transceiver(std::move(transceiver)) {
    _sender = RTCRtpSender::holder().GetOrCreate(_factory, _transceiver->sender());
    _receiver = RTCRtpReceiver::holder().GetOrCreate(_factory, _transceiver->receiver());
  }

  void RTCRtpTransceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpTransceiver, std::shared_ptr<RTCRtpTransceiver>>(m, "RTCRtpTransceiver")
        .def_property_readonly("mid", nogil_fn(&RTCRtpTransceiver::GetMid))
        .def_property_readonly("sender", nogil_fn(&RTCRtpTransceiver::GetSender))
        .def_property_readonly("receiver", nogil_fn(&RTCRtpTransceiver::GetReceiver))
        .def_property_readonly("stopped", nogil_fn(&RTCRtpTransceiver::GetStopped))
        .def_property_readonly("stopping", nogil_fn(&RTCRtpTransceiver::GetStopping))
        .def_property_readonly("kind", nogil_fn(&RTCRtpTransceiver::GetKind))
        .def_property("direction", nogil_fn(&RTCRtpTransceiver::GetDirection),
                      nogil_fn(&RTCRtpTransceiver::SetDirection))
        .def_property_readonly("currentDirection", nogil_fn(&RTCRtpTransceiver::GetCurrentDirection))
        .def("setCodecPreferences", &RTCRtpTransceiver::SetCodecPreferences, nogil(), pybind11::arg("codecs"))
        .def("getCodecPreferences", &RTCRtpTransceiver::GetCodecPreferences, nogil())
        .def("getHeaderExtensionsToNegotiate", &RTCRtpTransceiver::GetHeaderExtensionsToNegotiate, nogil())
        .def("setHeaderExtensionsToNegotiate", &RTCRtpTransceiver::SetHeaderExtensionsToNegotiate, nogil(),
             pybind11::arg("extensions"))
        .def("getNegotiatedHeaderExtensions", &RTCRtpTransceiver::GetNegotiatedHeaderExtensions, nogil())
        .def("stop", &RTCRtpTransceiver::Stop, nogil());
  }

  InstanceHolder<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> &RTCRtpTransceiver::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto *holder = new InstanceHolder<RTCRtpTransceiver, webrtc::RtpTransceiverInterface>();
    return *holder;
  }

  void RTCRtpTransceiver::SetConnection(std::weak_ptr<RTCPeerConnection> connection) {
    const std::scoped_lock lock(_mutex);
    _connection = std::move(connection);
  }

  std::optional<std::string> RTCRtpTransceiver::GetMid() {
    return _transceiver->mid();
  }

  std::shared_ptr<RTCRtpSender> RTCRtpTransceiver::GetSender() {
    return _sender;
  }

  std::shared_ptr<RTCRtpReceiver> RTCRtpTransceiver::GetReceiver() {
    return _receiver;
  }

  webrtc::MediaType RTCRtpTransceiver::GetKind() {
    return _transceiver->media_type();
  }

  bool RTCRtpTransceiver::GetStopped() {
    return _transceiver->stopped();
  }

  bool RTCRtpTransceiver::GetStopping() {
    return _transceiver->stopping();
  }

  webrtc::RtpTransceiverDirection RTCRtpTransceiver::GetDirection() {
    return _transceiver->direction();
  }

  void RTCRtpTransceiver::SetDirection(webrtc::RtpTransceiverDirection direction) {
    auto result = _transceiver->SetDirectionWithError(direction);
    if (!result.ok()) {
      throw RTCException(result);
    }
  }

  std::optional<webrtc::RtpTransceiverDirection> RTCRtpTransceiver::GetCurrentDirection() {
    return _transceiver->current_direction();
  }

  void RTCRtpTransceiver::Stop() {
    std::shared_ptr<RTCPeerConnection> connection;
    {
      const std::scoped_lock lock(_mutex);
      connection = _connection.lock();
    }
    if (!connection || connection->IsClosed()) {
      throw RTCException(closedError("stop", "RTCRtpTransceiver"));
    }
    auto result = _transceiver->StopStandard();
    if (!result.ok()) {
      throw RTCException(result);
    }
  }

  void RTCRtpTransceiver::SetCodecPreferences(std::vector<webrtc::RtpCodecCapability> codecs) {
    auto result = _transceiver->SetCodecPreferences(codecs);
    if (!result.ok()) {
      throw RTCException(result);
    }
  }

  std::vector<webrtc::RtpCodecCapability> RTCRtpTransceiver::GetCodecPreferences() {
    return _transceiver->codec_preferences();
  }

  std::vector<webrtc::RtpHeaderExtensionCapability> RTCRtpTransceiver::GetHeaderExtensionsToNegotiate() {
    return _transceiver->GetHeaderExtensionsToNegotiate();
  }

  void RTCRtpTransceiver::SetHeaderExtensionsToNegotiate(
      const std::vector<webrtc::RtpHeaderExtensionCapability> &extensions) {
    auto result = _transceiver->SetHeaderExtensionsToNegotiate(extensions);
    if (!result.ok()) {
      throw RTCException(result);
    }
  }

  std::vector<webrtc::RtpHeaderExtensionCapability> RTCRtpTransceiver::GetNegotiatedHeaderExtensions() {
    return _transceiver->GetNegotiatedHeaderExtensions();
  }

} // namespace python_webrtc
