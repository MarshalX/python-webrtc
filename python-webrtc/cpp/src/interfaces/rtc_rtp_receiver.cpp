//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_receiver.h"
#include "../utils/gil.h"

#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <rtc_base/time_utils.h>

namespace python_webrtc {

  RTCRtpReceiver::RTCRtpReceiver(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver
  ) : _factory(std::move(factory)), _receiver(std::move(receiver)) {
    // the track of a receiver is a remote one
    _track = MediaStreamTrack::holder().GetOrCreate(_factory, _receiver->track());
    _track->MarkRemote();
    // Posted, not blocking: wrappers are created under locks that the signaling thread may wait for.
    // The destructor unregisters with a call to the signaling thread, which runs after this.
    _factory->_signalingThread->PostTask(_alive.Guard([this]() { _receiver->SetObserver(this); }));
  }

  RTCRtpReceiver::~RTCRtpReceiver() {
    gil_release_if_held release;
    _factory->_signalingThread->BlockingCall([this]() { _receiver->SetObserver(nullptr); });
  }

  void RTCRtpReceiver::OnFirstPacketReceived(webrtc::MediaType media_type) {
    std::lock_guard<std::mutex> lock(_mutex);
    _track->SetMuted(false);
  }

  void RTCRtpReceiver::OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType media_type) {
    OnFirstPacketReceived(media_type);
  }

  void RTCRtpReceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpReceiver, std::shared_ptr<RTCRtpReceiver>>(m, "RTCRtpReceiver")
        .def_property_readonly("track", nogil_fn(&RTCRtpReceiver::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpReceiver::GetTransport))
        .def("getParameters", &RTCRtpReceiver::GetParameters, nogil())
        .def_property("jitterBufferTarget", nogil_fn(&RTCRtpReceiver::GetJitterBufferTarget),
                      nogil_fn(&RTCRtpReceiver::SetJitterBufferTarget))
        .def("getStats", &RTCRtpReceiver::GetStats, nogil())
        .def("_getSources", [](RTCRtpReceiver &self) {
          // (is a synchronization source, source, timestamp in ms since the Unix epoch, RTP timestamp,
          // audio level in -dBov), from the packets of the last 10 seconds, the most recent first
          std::vector<std::tuple<bool, uint32_t, double, uint32_t, std::optional<int>>> sources;
          // libwebrtc times the packets with its monotonic clock
          auto offset = static_cast<double>(webrtc::TimeUTCMillis() - webrtc::TimeMillis());
          for (const auto &source: self._receiver->GetSources()) {
            auto level = source.audio_level();
            sources.emplace_back(source.source_type() == webrtc::RtpSourceType::SSRC, source.source_id(),
                                 static_cast<double>(source.timestamp().ms()) + offset, source.rtp_timestamp(),
                                 level ? std::optional<int>(*level) : std::nullopt);
          }
          return sources;
        }, nogil())
        .def_static("getCapabilities", &RTCRtpReceiver::GetCapabilities, nogil());
  }

  InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &RTCRtpReceiver::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface>();
    return *holder;
  }

  std::shared_ptr<MediaStreamTrack> RTCRtpReceiver::GetTrack() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_track) {
      _track = MediaStreamTrack::holder().GetOrCreate(_factory, _receiver->track());
    }
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

  webrtc::RtpParameters RTCRtpReceiver::GetParameters() {
    auto parameters = _receiver->GetParameters();
    std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs;
    std::function<std::vector<webrtc::RtpExtension>()> negotiatedHeaderExtensions;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      negotiatedCodecs = _negotiatedCodecs;
      negotiatedHeaderExtensions = _negotiatedHeaderExtensions;
    }
    if (parameters.codecs.empty() && negotiatedCodecs) {
      parameters.codecs = negotiatedCodecs();
    }
    if (parameters.header_extensions.empty() && negotiatedHeaderExtensions) {
      parameters.header_extensions = negotiatedHeaderExtensions();
    }
    return parameters;
  }

  void RTCRtpReceiver::SetNegotiatedHeaderExtensions(
      std::function<std::vector<webrtc::RtpExtension>()> negotiatedHeaderExtensions) {
    std::lock_guard<std::mutex> lock(_mutex);
    _negotiatedHeaderExtensions = std::move(negotiatedHeaderExtensions);
  }

  std::optional<webrtc::RtpCapabilities> RTCRtpReceiver::GetCapabilities(const std::string &kind) {
    webrtc::MediaType type;
    if (kind == "audio") {
      type = webrtc::MediaType::AUDIO;
    } else if (kind == "video") {
      type = webrtc::MediaType::VIDEO;
    } else {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpReceiverCapabilities(type);
  }

  void RTCRtpReceiver::SetNegotiatedCodecs(std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs) {
    std::lock_guard<std::mutex> lock(_mutex);
    _negotiatedCodecs = std::move(negotiatedCodecs);
  }

  void RTCRtpReceiver::SetStatsGetter(StatsGetter getStats) {
    std::lock_guard<std::mutex> lock(_mutex);
    _getStats = std::move(getStats);
  }

  void RTCRtpReceiver::GetStats(std::function<void(std::string)> &onSuccess,
                          std::function<void(RTCCallbackException)> &onFailure) {
    StatsGetter getStats;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      getStats = _getStats;
    }
    if (!getStats) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RtpReceiver has no connection"));
      return;
    }
    getStats(onSuccess, onFailure);
  }

} // namespace python_webrtc
