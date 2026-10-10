//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_receiver.h"

#include <rtc_base/time_utils.h>

#include <pybind11/stl.h>

#include "../enums/enums.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"
#include "rtc_peer_connection/rtc_peer_connection.h"

namespace python_webrtc {

  RTCRtpReceiver::RTCRtpReceiver(std::shared_ptr<PeerConnectionFactory> factory,
                                 webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver)
      : _factory(std::move(factory)), _receiver(std::move(receiver)),
        _track(MediaStreamTrack::registry().GetOrCreate(_factory, _receiver->track())) {
    // the track of a receiver is a remote one
    _track->MarkRemote();
    _factory->signalingThread()->PostTask(Guard([this]() {
      _receiver->SetObserver(this);
      registry().SetObserver(_receiver.get(), this);
    }));
  }

  RTCRtpReceiver::~RTCRtpReceiver() {
    // callbacks run on the signaling thread, so after this none of them can be running or start again
    BlockingCallOn(_factory->signalingThread(), [this]() {
      // a newer wrapper of the receiver may have taken its single observer slot
      if (registry().TakeObserver(_receiver.get(), this)) {
        _receiver->SetObserver(nullptr);
      }
    });
  }

  void RTCRtpReceiver::OnFirstPacketReceived(webrtc::MediaType /*mediaType*/) {
    _track->SetMuted(false);
  }

  void RTCRtpReceiver::OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType mediaType) {
    OnFirstPacketReceived(mediaType);
  }

  void RTCRtpReceiver::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpReceiver, std::shared_ptr<RTCRtpReceiver>>(m, "RTCRtpReceiver")
        .def_property_readonly("_id", &RTCRtpReceiver::Id)
        .def_property_readonly("track", nogil_fn(&RTCRtpReceiver::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpReceiver::GetTransport))
        .def_property("jitterBufferTarget", nogil_fn(&RTCRtpReceiver::GetJitterBufferTarget),
                      nogil_fn(&RTCRtpReceiver::SetJitterBufferTarget))
        .def("getParameters", &RTCRtpReceiver::GetParameters, nogil())
        .def("getStats", &RTCRtpReceiver::GetStats, nogil(), pybind11::arg("mailbox"), pybind11::arg("token"))
        .def_static("getCapabilities", &RTCRtpReceiver::GetCapabilities, nogil(), pybind11::arg("kind"))
        .def_property("transform", nogil_fn(&RTCRtpReceiver::GetTransform), nogil_fn(&RTCRtpReceiver::SetTransform))
        .def("_getSources", &RTCRtpReceiver::GetSources, nogil());
  }

  Registry<RTCRtpReceiver, webrtc::RtpReceiverInterface> &RTCRtpReceiver::registry() {
    static ForkLocal<Registry<RTCRtpReceiver, webrtc::RtpReceiverInterface>> registry;
    return registry.Get();
  }

  void RTCRtpReceiver::SetConnection(std::weak_ptr<RTCPeerConnection> connection) {
    const std::scoped_lock lock(_mutex);
    _connection = std::move(connection);
  }

  std::shared_ptr<RTCPeerConnection> RTCRtpReceiver::GetConnection() {
    const std::scoped_lock lock(_mutex);
    return _connection.lock();
  }

  std::shared_ptr<MediaStreamTrack> RTCRtpReceiver::GetTrack() {
    return _track;
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpReceiver::GetTransport() {
    auto transport = _receiver->dtls_transport();
    // wrapped out of the lock: wrapping may wait for the signaling thread
    auto wrapper = RTCDtlsTransport::registry().GetOrCreate(_factory, transport);

    std::shared_ptr<RTCDtlsTransport> previous;
    const std::scoped_lock lock(_mutex);
    if (!_transport || _transport->transport() != transport) {
      previous = std::move(_transport);
      _transport = std::move(wrapper);
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
    const std::scoped_lock lock(_mutex);
    return _jitterBufferTarget;
  }

  void RTCRtpReceiver::SetJitterBufferTarget(std::optional<double> target) {
    {
      const std::scoped_lock lock(_mutex);
      _jitterBufferTarget = target;
    }
    // milliseconds in Python, seconds in libwebrtc
    constexpr double msPerSecond = 1000;
    _receiver->SetJitterBufferMinimumDelay(target ? std::optional<double>(*target / msPerSecond) : std::nullopt);
  }

  void RTCRtpReceiver::GetStats(std::shared_ptr<Mailbox> mailbox, uint64_t token) {
    Completion completion(std::move(mailbox), token);
    auto connection = GetConnection();
    if (!connection) {
      completion.Fail(RTCCallbackException(closedError("getStats", "RTCRtpReceiver")));
      return;
    }
    connection->CollectStats(_receiver, std::move(completion));
  }

  std::vector<RTCRtpReceiver::Source> RTCRtpReceiver::GetSources() {
    std::vector<Source> sources;
    // libwebrtc times the packets with its monotonic clock
    auto offset = static_cast<double>(webrtc::TimeUTCMillis() - webrtc::TimeMillis());
    for (const auto &source : _receiver->GetSources()) {
      auto level = source.audio_level();
      sources.emplace_back(source.source_type() == webrtc::RtpSourceType::SSRC, source.source_id(),
                           static_cast<double>(source.timestamp().ms()) + offset, source.rtp_timestamp(),
                           level ? std::optional<int>(*level) : std::nullopt);
    }
    return sources;
  }

  FrameSource RTCRtpReceiver::TransformSource() {
    FrameSource source;
    source.sender = false;
    source.video = _receiver->media_type() == webrtc::MediaType::VIDEO;
    source.sendKeyFrameRequest = [weak = weak_from_this()]() {
      auto self = weak.lock();
      if (!self) {
        return;
      }
      // the source of a remote video track asks the receiver's stream for a key frame (a PLI)
      auto track = self->_receiver->track();
      auto *video = dynamic_cast<webrtc::VideoTrackInterface *>(track.get());
      if (video != nullptr && video->GetSource() != nullptr) {
        video->GetSource()->GenerateKeyFrame();
      }
    };
    return source;
  }

  void RTCRtpReceiver::SetTransform(const std::shared_ptr<RtpTransform> &transform) {
    _transform.Set(
        transform, [this]() { return TransformSource(); },
        [this](const webrtc::scoped_refptr<FrameTransformerBridge> &bridge) {
          _receiver->SetFrameTransformer(bridge);
        });
  }

  std::optional<webrtc::RtpCapabilities> RTCRtpReceiver::GetCapabilities(const std::string &kind) {
    auto type = mediaTypeOf(kind);
    if (!type) {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpReceiverCapabilities(*type);
  }

} // namespace python_webrtc
