//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_receiver.h"

#include <rtc_base/time_utils.h>

#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "rtc_peer_connection.h"
#include "../enums/enums.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  RTCRtpReceiver::RTCRtpReceiver(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver
  ) : _factory(std::move(factory)), _receiver(std::move(receiver)),
      _track(MediaStreamTrack::holder().GetOrCreate(_factory, _receiver->track())) {
    // the track of a receiver is a remote one
    _track->MarkRemote();
    // see AliveGuard
    _factory->_signalingThread->PostTask(_alive.Guard([this]() { _receiver->SetObserver(this); }));
  }

  RTCRtpReceiver::~RTCRtpReceiver() {
    BlockingDestructor release("RTCRtpReceiver");

    // the receiver has a single observer slot, a newer wrapper of it may have taken it over already
    auto replaced = holder().HasLive(_receiver.get());
    // callbacks run on the signaling thread, so after this none of them can be running or start again
    _factory->_signalingThread->BlockingCall([this, replaced]() {
      if (!replaced) {
        _receiver->SetObserver(nullptr);
      }
    });
  }

  void RTCRtpReceiver::OnFirstPacketReceived(webrtc::MediaType) {
    _track->SetMuted(false);
  }

  void RTCRtpReceiver::OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType mediaType) {
    OnFirstPacketReceived(mediaType);
  }

  void RTCRtpReceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpReceiver, std::shared_ptr<RTCRtpReceiver>>(m, "RTCRtpReceiver")
        .def_property_readonly("track", nogil_fn(&RTCRtpReceiver::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpReceiver::GetTransport))
        .def_property("jitterBufferTarget", nogil_fn(&RTCRtpReceiver::GetJitterBufferTarget),
                      nogil_fn(&RTCRtpReceiver::SetJitterBufferTarget))
        .def("getParameters", &RTCRtpReceiver::GetParameters, nogil())
        .def("getStats", &RTCRtpReceiver::GetStats, nogil(), pybind11::arg("onSuccess"), pybind11::arg("onFailure"))
        .def_static("getCapabilities", &RTCRtpReceiver::GetCapabilities, nogil(), pybind11::arg("kind"))
        .def("_getSources", &RTCRtpReceiver::GetSources, nogil());
  }

  InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &RTCRtpReceiver::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface>();
    return *holder;
  }

  void RTCRtpReceiver::SetConnection(std::weak_ptr<RTCPeerConnection> connection) {
    std::lock_guard<std::mutex> lock(_mutex);
    _connection = std::move(connection);
  }

  std::shared_ptr<RTCPeerConnection> RTCRtpReceiver::GetConnection() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _connection.lock();
  }

  std::shared_ptr<MediaStreamTrack> RTCRtpReceiver::GetTrack() {
    return _track;
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpReceiver::GetTransport() {
    auto transport = _receiver->dtls_transport();

    std::shared_ptr<RTCDtlsTransport> previous;
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_transport || _transport->transport() != transport) {
      previous = std::move(_transport);
      _transport = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);
    }

    if (_transport) {
      return _transport;
    }
    return {};
  }

  webrtc::RtpParameters RTCRtpReceiver::GetParameters() {
    auto parameters = _receiver->GetParameters();
    auto connection = GetConnection();
    if (!connection) {
      return parameters;
    }
    if (parameters.codecs.empty()) {
      parameters.codecs = connection->NegotiatedCodecs(_receiver);
    }
    if (parameters.header_extensions.empty()) {
      parameters.header_extensions = connection->NegotiatedHeaderExtensions(_receiver);
    }
    return parameters;
  }

  std::optional<double> RTCRtpReceiver::GetJitterBufferTarget() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _jitterBufferTarget;
  }

  void RTCRtpReceiver::SetJitterBufferTarget(std::optional<double> target) {
    {
      std::lock_guard<std::mutex> lock(_mutex);
      _jitterBufferTarget = target;
    }
    _receiver->SetJitterBufferMinimumDelay(target ? std::optional<double>(*target / 1000) : std::nullopt);
  }

  void RTCRtpReceiver::GetStats(std::function<void(std::string)> &onSuccess,
                                std::function<void(RTCCallbackException)> &onFailure) {
    auto connection = GetConnection();
    if (!connection) {
      onFailure(RTCCallbackException(closedError("getStats", "RTCRtpReceiver")));
      return;
    }
    connection->CollectStats(_receiver, onSuccess, onFailure);
  }

  std::vector<RTCRtpReceiver::Source> RTCRtpReceiver::GetSources() {
    std::vector<Source> sources;
    // libwebrtc times the packets with its monotonic clock
    auto offset = static_cast<double>(webrtc::TimeUTCMillis() - webrtc::TimeMillis());
    for (const auto &source: _receiver->GetSources()) {
      auto level = source.audio_level();
      sources.emplace_back(source.source_type() == webrtc::RtpSourceType::SSRC, source.source_id(),
                           static_cast<double>(source.timestamp().ms()) + offset, source.rtp_timestamp(),
                           level ? std::optional<int>(*level) : std::nullopt);
    }
    return sources;
  }

  std::optional<webrtc::RtpCapabilities> RTCRtpReceiver::GetCapabilities(const std::string &kind) {
    auto type = mediaTypeOf(kind);
    if (!type) {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpReceiverCapabilities(*type);
  }

} // namespace python_webrtc
