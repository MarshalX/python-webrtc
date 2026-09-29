//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_sender.h"

#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "rtc_peer_connection.h"
#include "../enums/enums.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(std::move(factory)), _sender(std::move(sender)) {}

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender, std::shared_ptr<RTCRtpSender>>(m, "RTCRtpSender")
        .def_property_readonly("track", nogil_fn(&RTCRtpSender::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpSender::GetTransport))
        .def_property_readonly("kind", nogil_fn(&RTCRtpSender::GetKind))
        .def_property_readonly("dtmf", nogil_fn(&RTCRtpSender::GetDtmf))
        .def("getParameters", &RTCRtpSender::GetParameters, nogil())
        .def("setParameters", &RTCRtpSender::SetParameters, nogil(),
             pybind11::arg("onSuccess"), pybind11::arg("onFailure"), pybind11::arg("parameters"))
        .def("replaceTrack", &RTCRtpSender::ReplaceTrack, nogil(), pybind11::arg("track"))
        .def("setStreams", &RTCRtpSender::SetStreams, nogil(), pybind11::arg("streamIds"))
        .def("getStreamIds", &RTCRtpSender::GetStreamIds, nogil())
        .def("getStats", &RTCRtpSender::GetStats, nogil(), pybind11::arg("onSuccess"), pybind11::arg("onFailure"))
        .def_static("getCapabilities", &RTCRtpSender::GetCapabilities, nogil(), pybind11::arg("kind"))
        .def("_transceiverStopped", &RTCRtpSender::IsTransceiverStopped, nogil())
        .def("_lastParameters", &RTCRtpSender::GetLastParameters, nogil())
        .def("_expireParameters", &RTCRtpSender::ExpireParameters, nogil(),
             pybind11::arg("transactionId") = std::nullopt);
  }

  InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &RTCRtpSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface>();
    return *holder;
  }

  void RTCRtpSender::SetConnection(std::weak_ptr<RTCPeerConnection> connection) {
    std::lock_guard<std::mutex> lock(_mutex);
    _connection = std::move(connection);
    if (_dtmf) {
      _dtmf->SetTransceiver(TransceiverGetter());
    }
  }

  std::shared_ptr<RTCPeerConnection> RTCRtpSender::GetConnection() {
    std::lock_guard<std::mutex> lock(_mutex);
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
    std::lock_guard<std::mutex> lock(_mutex);
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
    std::lock_guard<std::mutex> lock(_mutex);
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
    std::lock_guard<std::mutex> lock(_mutex);
    if (wrapper && _dtmf != wrapper) {
      _dtmf = std::move(wrapper);
      _dtmf->SetTransceiver(TransceiverGetter());
    }
    return dtmf ? _dtmf : nullptr;
  }

  webrtc::RtpParameters RTCRtpSender::GetParameters() {
    {
      // the same parameters until they expire
      std::lock_guard<std::mutex> lock(_mutex);
      if (_lastParameters) {
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
    std::lock_guard<std::mutex> lock(_mutex);
    _lastParameters = parameters;
    return parameters;
  }

  std::optional<webrtc::RtpParameters> RTCRtpSender::GetLastParameters() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _lastParameters;
  }

  void RTCRtpSender::ExpireParameters(const std::optional<std::string> &transactionId) {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_lastParameters && (!transactionId || _lastParameters->transaction_id == *transactionId)) {
      _lastParameters.reset();
    }
  }

  void RTCRtpSender::SetParameters(std::function<void()> &onSuccess,
                                   std::function<void(RTCCallbackException)> &onFailure,
                                   const webrtc::RtpParameters &parameters) {
    {
      std::lock_guard<std::mutex> lock(_mutex);
      if (!_lastParameters) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE,
            "getParameters() must be called before setParameters(), in the same task"));
        return;
      }
      if (_lastParameters->transaction_id != parameters.transaction_id) {
        onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
            "The transactionId doesn't match the one of the last getParameters()"));
        return;
      }
    }
    // the parameters can be set again until they expire, while libwebrtc takes a transaction id only once
    auto fresh = _sender->GetParameters();
    // libwebrtc aborts the process on encodings that don't match its layers (like after renegotiation)
    bool sameLayers = fresh.encodings.size() == parameters.encodings.size();
    for (size_t i = 0; sameLayers && i < fresh.encodings.size(); ++i) {
      sameLayers = fresh.encodings[i].rid == parameters.encodings[i].rid;
    }
    if (!sameLayers) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_MODIFICATION,
          "The encodings of the sender changed since getParameters()"));
      return;
    }
    auto current = parameters;
    current.transaction_id = fresh.transaction_id;
    // read-only: getParameters() shows the negotiated codecs this side can send, libwebrtc takes its own list
    current.codecs = fresh.codecs;
    _sender->SetParametersAsync(current, [onSuccess, onFailure](webrtc::RTCError error) {
      if (error.ok()) {
        onSuccess();
      } else {
        onFailure(RTCCallbackException(std::move(error)));
      }
    });
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

  std::optional<webrtc::RtpCapabilities> RTCRtpSender::GetCapabilities(const std::string &kind) {
    auto type = mediaTypeOf(kind);
    if (!type) {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpSenderCapabilities(*type);
  }

} // namespace python_webrtc
