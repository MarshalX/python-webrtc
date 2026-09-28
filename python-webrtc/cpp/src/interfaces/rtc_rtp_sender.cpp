//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_rtp_sender.h"
#include "rtc_peer_connection.h"
#include "../utils/gil.h"

#include <pybind11/functional.h>
#include <pybind11/stl.h>

namespace python_webrtc {

  RTCRtpSender::RTCRtpSender(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender)
      : _factory(std::move(factory)), _sender(std::move(sender)) {}

  void RTCRtpSender::Init(pybind11::module &m) {
    pybind11::class_<RTCRtpSender, std::shared_ptr<RTCRtpSender>>(m, "RTCRtpSender")
        .def_property_readonly("track", nogil_fn(&RTCRtpSender::GetTrack))
        .def_property_readonly("transport", nogil_fn(&RTCRtpSender::GetTransport))
        .def_property_readonly("kind", nogil_fn([](RTCRtpSender &self) { return self._sender->media_type(); }))
        .def_property_readonly("dtmf", nogil_fn(&RTCRtpSender::GetDtmf))
        .def("getParameters", &RTCRtpSender::GetParameters, nogil())
        .def("_transceiverStopped", [](RTCRtpSender &self) {
          std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> lookup;
          {
            std::lock_guard<std::mutex> lock(self._mutex);
            lookup = self._transceiver;
          }
          auto transceiver = lookup ? lookup() : nullptr;
          return !transceiver || transceiver->stopping() || transceiver->stopped();
        }, nogil())
        .def("getStats", &RTCRtpSender::GetStats, nogil())
        .def_property_readonly("_connection", nogil_fn(&RTCRtpSender::GetConnection))
        .def("_lastParameters", &RTCRtpSender::GetLastParameters, nogil())
        .def("_expireParameters", &RTCRtpSender::ExpireParameters, nogil(),
             pybind11::arg("transactionId") = std::nullopt)
        .def("setParameters", &RTCRtpSender::SetParameters, nogil())
        .def("replaceTrack", &RTCRtpSender::ReplaceTrack, nogil())
        .def("setStreams", &RTCRtpSender::SetStreams, nogil())
        .def("getStreamIds", &RTCRtpSender::GetStreamIds, nogil())
        .def_static("getCapabilities", &RTCRtpSender::GetCapabilities, nogil());
  }

  InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &RTCRtpSender::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface>();
    return *holder;
  }

  std::optional<std::shared_ptr<MediaStreamTrack>> RTCRtpSender::GetTrack() {
    auto track = _sender->track();

    std::shared_ptr<MediaStreamTrack> previous;
    std::lock_guard<std::mutex> lock(_mutex);
    if (!_track || _track->track() != track) {
      previous = std::move(_track);
      _track = MediaStreamTrack::holder().GetOrCreate(_factory, track);
    }

    if (_track) {
      return _track;
    }
    return {};
  }

  std::optional<std::shared_ptr<RTCDtlsTransport>> RTCRtpSender::GetTransport() {
    auto transport = _sender->dtls_transport();

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

  webrtc::RtpParameters RTCRtpSender::GetParameters() {
    {
      // the same parameters until they expire
      std::lock_guard<std::mutex> lock(_mutex);
      if (_lastParameters) {
        return *_lastParameters;
      }
    }
    auto parameters = _sender->GetParameters();
    std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      negotiatedCodecs = _negotiatedCodecs;
    }
    // the negotiated codecs this side can send (libwebrtc also lists remote codecs it doesn't know),
    // read out of the lock: it's a call to the signaling thread
    auto negotiated = negotiatedCodecs ? negotiatedCodecs() : std::vector<webrtc::RtpCodecParameters>();
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
        onFailure(wrapRTCErrorForCallback(error));
      }
    });
  }

  bool RTCRtpSender::ReplaceTrack(std::optional<std::reference_wrapper<MediaStreamTrack>> track) {
    return _sender->SetTrack(track ? track->get().track().get() : nullptr);
  }

  void RTCRtpSender::SetTransceiver(
      std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver) {
    std::lock_guard<std::mutex> lock(_mutex);
    _transceiver = std::move(transceiver);
    if (_dtmf) {
      _dtmf->SetTransceiver(_transceiver);
    }
  }

  std::shared_ptr<RTCDTMFSender> RTCRtpSender::GetDtmf() {
    auto dtmf = _sender->GetDtmfSender();
    std::lock_guard<std::mutex> lock(_mutex);
    if (dtmf && (!_dtmf || _dtmf.get() != RTCDTMFSender::holder().Find(dtmf.get()).get())) {
      _dtmf = RTCDTMFSender::holder().GetOrCreate(_factory, dtmf);
      _dtmf->SetTransceiver(_transceiver);
    }
    return dtmf ? _dtmf : nullptr;
  }

  void RTCRtpSender::SetConnection(std::function<std::shared_ptr<RTCPeerConnection>()> connection) {
    std::lock_guard<std::mutex> lock(_mutex);
    _connection = std::move(connection);
  }

  std::shared_ptr<RTCPeerConnection> RTCRtpSender::GetConnection() {
    std::function<std::shared_ptr<RTCPeerConnection>()> connection;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      connection = _connection;
    }
    return connection ? connection() : nullptr;
  }

  void RTCRtpSender::SetConnectionClosed(std::function<bool()> connectionClosed) {
    std::lock_guard<std::mutex> lock(_mutex);
    _connectionClosed = std::move(connectionClosed);
  }

  void RTCRtpSender::SetStreams(const std::vector<std::string> &streamIds) {
    std::function<bool()> connectionClosed;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      connectionClosed = _connectionClosed;
    }
    if (connectionClosed && connectionClosed()) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "The RTCPeerConnection is closed");
    }
    _sender->SetStreams(streamIds);
  }

  std::vector<std::string> RTCRtpSender::GetStreamIds() {
    return _sender->stream_ids();
  }

  std::optional<webrtc::RtpCapabilities> RTCRtpSender::GetCapabilities(const std::string &kind) {
    webrtc::MediaType type;
    if (kind == "audio") {
      type = webrtc::MediaType::AUDIO;
    } else if (kind == "video") {
      type = webrtc::MediaType::VIDEO;
    } else {
      return std::nullopt;
    }
    return PeerConnectionFactory::GetOrCreateDefault()->factory()->GetRtpSenderCapabilities(type);
  }

  void RTCRtpSender::SetNegotiatedCodecs(std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs) {
    std::lock_guard<std::mutex> lock(_mutex);
    _negotiatedCodecs = std::move(negotiatedCodecs);
  }

  void RTCRtpSender::SetStatsGetter(StatsGetter getStats) {
    std::lock_guard<std::mutex> lock(_mutex);
    _getStats = std::move(getStats);
  }

  void RTCRtpSender::GetStats(std::function<void(std::string)> &onSuccess,
                          std::function<void(RTCCallbackException)> &onFailure) {
    StatsGetter getStats;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      getStats = _getStats;
    }
    if (!getStats) {
      onFailure(RTCCallbackException(webrtc::RTCErrorType::INVALID_STATE, "The RtpSender has no connection"));
      return;
    }
    getStats(onSuccess, onFailure);
  }

} // namespace python_webrtc
