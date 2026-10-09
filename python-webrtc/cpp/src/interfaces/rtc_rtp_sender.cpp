//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_sender.h"
#include "../utils/python_callback.h"

#include <algorithm>
#include <functional>
#include <memory>
#include <utility>

#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "../enums/enums.h"
#include "../utils/gil.h"
#include "rtc_peer_connection/rtc_peer_connection.h"

namespace python_webrtc {

  namespace {

    // libwebrtc drops the callback of SetParametersAsync without calling it when the sender has no media channel
    // (like after a rollback of its offer) or loses it meanwhile: rejects like it does once the channel is gone
    class SetParametersCompletion final {
    public:
      SetParametersCompletion(std::function<void()> onSuccess, std::function<void(RTCCallbackException)> onFailure)
          : _onSuccess(std::move(onSuccess)), _onFailure(std::move(onFailure)) {}
      SetParametersCompletion(const SetParametersCompletion &) = delete;
      SetParametersCompletion(SetParametersCompletion &&) = delete;
      SetParametersCompletion &operator=(const SetParametersCompletion &) = delete;
      SetParametersCompletion &operator=(SetParametersCompletion &&) = delete;

      ~SetParametersCompletion() {
        if (_onFailure) {
          _onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
                                          "The sender was detached before the parameters were set"));
        }
      }

      void operator()(webrtc::RTCError error) {
        auto onSuccess = std::exchange(_onSuccess, nullptr);
        auto onFailure = std::exchange(_onFailure, nullptr);
        if (error.ok()) {
          onSuccess();
        } else {
          onFailure(RTCCallbackException(std::move(error)));
        }
      }

    private:
      std::function<void()> _onSuccess;
      std::function<void(RTCCallbackException)> _onFailure;
    };

    // only what setParameters may change, as in Chromium
    void applySettable(const webrtc::RtpEncodingParameters &requested, webrtc::RtpEncodingParameters &current) {
      current.active = requested.active;
      current.request_key_frame = requested.request_key_frame;
      current.max_bitrate_bps = requested.max_bitrate_bps;
      current.max_framerate = requested.max_framerate;
      current.scale_resolution_down_by = requested.scale_resolution_down_by;
      current.scalability_mode = requested.scalability_mode;
      current.bitrate_priority = requested.bitrate_priority;
      current.network_priority = requested.network_priority;
      current.adaptive_ptime = requested.adaptive_ptime;
      current.codec = requested.codec;
    }

  } // namespace

  RTCRtpSender::RTCRtpSender(std::shared_ptr<PeerConnectionFactory> factory,
                             webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(std::move(factory)), _sender(std::move(sender)) {}

  RTCRtpSender::~RTCRtpSender() {
    _transform.Release();
  }

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender, std::shared_ptr<RTCRtpSender>>(m, "RTCRtpSender")
        .def_property_readonly("track", nogil_fn(&RTCRtpSender::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpSender::GetTransport))
        .def_property_readonly("kind", nogil_fn(&RTCRtpSender::GetKind))
        .def_property_readonly("dtmf", nogil_fn(&RTCRtpSender::GetDtmf))
        .def("getParameters", &RTCRtpSender::GetParameters, nogil())
        .def("setParameters", WithCallbacks(&RTCRtpSender::SetParameters), pybind11::arg("onSuccess"),
             pybind11::arg("onFailure"), pybind11::arg("parameters"))
        .def("replaceTrack", &RTCRtpSender::ReplaceTrack, nogil(), pybind11::arg("track"))
        .def("setStreams", &RTCRtpSender::SetStreams, nogil(), pybind11::arg("streamIds"))
        .def("getStreamIds", &RTCRtpSender::GetStreamIds, nogil())
        .def("getStats", WithCallbacks(&RTCRtpSender::GetStats), pybind11::arg("onSuccess"), pybind11::arg("onFailure"))
        .def_static("getCapabilities", &RTCRtpSender::GetCapabilities, nogil(), pybind11::arg("kind"))
        .def_property("transform", nogil_fn(&RTCRtpSender::GetTransform), nogil_fn(&RTCRtpSender::SetTransform))
        .def("_transceiverStopped", &RTCRtpSender::IsTransceiverStopped, nogil())
        .def("_lastParameters", &RTCRtpSender::GetLastParameters, nogil())
        .def("_expireParameters", &RTCRtpSender::ExpireParameters, nogil(),
             pybind11::arg("transactionId") = std::nullopt)
        .def("_clearParameters", &RTCRtpSender::ClearParameters, nogil());
  }

  InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &RTCRtpSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto *holder = new InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface>();
    return *holder;
  }

  void RTCRtpSender::SetConnection(std::weak_ptr<RTCPeerConnection> connection) {
    const std::scoped_lock lock(_mutex);
    _connection = std::move(connection);
    if (_dtmf) {
      _dtmf->SetTransceiver(TransceiverGetter());
    }
  }

  std::shared_ptr<RTCPeerConnection> RTCRtpSender::GetConnection() {
    const std::scoped_lock lock(_mutex);
    return _connection.lock();
  }

  std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> RTCRtpSender::TransceiverGetter() {
    return [connection = _connection, sender = _sender]() -> webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> {
      auto pc = connection.lock();
      return pc ? pc->TransceiverOf(sender) : nullptr;
    };
  }

  std::optional<std::shared_ptr<MediaStreamTrack>> RTCRtpSender::GetTrack() {
    auto track = _sender->track();
    // wrapped out of the lock: wrapping may wait for the signaling thread
    auto wrapper = MediaStreamTrack::holder().GetOrCreate(_factory, track);

    std::shared_ptr<MediaStreamTrack> previous;
    const std::scoped_lock lock(_mutex);
    if (!_track || _track->track() != track) {
      previous = std::move(_track);
      _track = std::move(wrapper);
    }

    if (_track) {
      return _track;
    }
    return {};
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpSender::GetTransport() {
    auto transport = _sender->dtls_transport();
    // see GetTrack
    auto wrapper = RTCDtlsTransport::holder().GetOrCreate(_factory, transport);

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

  webrtc::MediaType RTCRtpSender::GetKind() {
    return _sender->media_type();
  }

  std::shared_ptr<RTCDTMFSender> RTCRtpSender::GetDtmf() {
    auto dtmf = _sender->GetDtmfSender();
    // see GetTrack
    auto wrapper = RTCDTMFSender::holder().GetOrCreate(_factory, dtmf);
    const std::scoped_lock lock(_mutex);
    if (wrapper && _dtmf != wrapper) {
      _dtmf = std::move(wrapper);
      _dtmf->SetTransceiver(TransceiverGetter());
    }
    return dtmf ? _dtmf : nullptr;
  }

  webrtc::RtpParameters RTCRtpSender::GetParameters() {
    {
      // the same parameters until they expire
      const std::scoped_lock lock(_mutex);
      if (_lastParameters && !_lastParametersExpired) {
        return *_lastParameters;
      }
    }
    auto parameters = _sender->GetParameters();
    // the negotiated codecs this side can send (libwebrtc also lists remote codecs it doesn't know),
    // read out of the lock: it's a call to the signaling thread
    auto connection = GetConnection();
    auto negotiated = connection ? connection->NegotiatedCodecs(_sender) : std::vector<webrtc::RtpCodecParameters>();
    if (!negotiated.empty()) {
      parameters.codecs = std::move(negotiated);
    }
    const std::scoped_lock lock(_mutex);
    _lastParameters = parameters;
    _lastParametersExpired = false;
    return parameters;
  }

  std::optional<webrtc::RtpParameters> RTCRtpSender::GetLastParameters() {
    const std::scoped_lock lock(_mutex);
    return _lastParameters;
  }

  void RTCRtpSender::ExpireParameters(const std::optional<std::string> &transactionId) {
    const std::scoped_lock lock(_mutex);
    if (_lastParameters && (!transactionId || _lastParameters->transaction_id == *transactionId)) {
      _lastParametersExpired = true;
    }
  }

  void RTCRtpSender::ClearParameters() {
    const std::scoped_lock lock(_mutex);
    _lastParameters.reset();
  }

  void RTCRtpSender::SetParameters(std::function<void()> &onSuccess,
                                   std::function<void(RTCCallbackException)> &onFailure,
                                   const webrtc::RtpParameters &parameters) {
    {
      const std::scoped_lock lock(_mutex);
      if (!_lastParameters) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
                                       "getParameters() must be called before setParameters()"));
        return;
      }
      if (_lastParameters->transaction_id != parameters.transaction_id) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
                                       "The transactionId doesn't match the one of the last getParameters()"));
        return;
      }
    }
    // libwebrtc takes the transaction id of its own last parameters, once
    auto current = _sender->GetParameters();
    // libwebrtc aborts the process on encodings that don't match its layers (like after renegotiation)
    bool sameLayers = current.encodings.size() == parameters.encodings.size();
    for (size_t i = 0; sameLayers && i < current.encodings.size(); ++i) {
      sameLayers = current.encodings[i].rid == parameters.encodings[i].rid;
    }
    if (!sameLayers) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
                                     "The encodings of the sender changed since getParameters()"));
      return;
    }
    // the rest, like SSRCs, may have changed since getParameters
    for (size_t i = 0; i < current.encodings.size(); ++i) {
      applySettable(parameters.encodings[i], current.encodings[i]);
    }
    current.degradation_preference = parameters.degradation_preference;
    _sender->SetParametersAsync(current, [completion = std::make_unique<SetParametersCompletion>(onSuccess, onFailure)](
                                             webrtc::RTCError error) { (*completion)(std::move(error)); });
  }

  bool RTCRtpSender::ReplaceTrack(std::optional<std::reference_wrapper<MediaStreamTrack>> track) {
    return _sender->SetTrack(track ? track->get().track().get() : nullptr);
  }

  void RTCRtpSender::SetStreams(const std::vector<std::string> &streamIds) {
    auto connection = GetConnection();
    if (!connection || connection->IsClosed()) {
      throw RTCException(closedError("setStreams", "RTCRtpSender"));
    }
    _sender->SetStreams(streamIds);
  }

  std::vector<std::string> RTCRtpSender::GetStreamIds() {
    return _sender->stream_ids();
  }

  void RTCRtpSender::GetStats(std::function<void(std::string)> &onSuccess,
                              std::function<void(RTCCallbackException)> &onFailure) {
    auto connection = GetConnection();
    if (!connection) {
      onFailure(RTCCallbackException(closedError("getStats", "RTCRtpSender")));
      return;
    }
    connection->CollectStats(_sender, onSuccess, onFailure);
  }

  bool RTCRtpSender::IsTransceiverStopped() {
    auto connection = GetConnection();
    auto transceiver = connection ? connection->TransceiverOf(_sender) : nullptr;
    return !transceiver || transceiver->stopping() || transceiver->stopped();
  }

  FrameSource RTCRtpSender::TransformSource() {
    FrameSource source;
    source.sender = true;
    source.video = _sender->media_type() == webrtc::MediaType::VIDEO;
    source.generateKeyFrame = [weak = weak_from_this()](const std::vector<std::string> &rids) {
      auto self = weak.lock();
      if (!self) {
        return FrameSource::KeyFrameResult::kRequested;
      }
      auto encodings = self->_sender->GetParameters().encodings;
      for (const auto &rid : rids) {
        // a single encoding is no layer of a rid, even if it kept the rid of simulcast negotiated away
        if (encodings.size() < 2 ||
            std::ranges::none_of(encodings, [&](const auto &encoding) { return encoding.rid == rid; })) {
          return FrameSource::KeyFrameResult::kUnknownRid;
        }
      }
      // fails only for a rid, checked above
      (void)self->_sender->GenerateKeyFrame(rids);
      return FrameSource::KeyFrameResult::kRequested;
    };
    return source;
  }

  void RTCRtpSender::SetTransform(const std::shared_ptr<RtpTransform> &transform) {
    _transform.Set(
        transform, [this]() { return TransformSource(); },
        [this](const webrtc::scoped_refptr<FrameTransformerBridge> &bridge) { _sender->SetFrameTransformer(bridge); });
  }

  std::optional<webrtc::RtpCapabilities> RTCRtpSender::GetCapabilities(const std::string &kind) {
    auto type = mediaTypeOf(kind);
    if (!type) {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpSenderCapabilities(*type);
  }

} // namespace python_webrtc
