//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>

#include <api/rtp_sender_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"
#include "../exceptions.h"
#include "rtc_dtmf_sender.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpSender {
  public:
    explicit RTCRtpSender(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpSenderInterface>);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &holder();

    std::optional<std::shared_ptr<MediaStreamTrack>> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender() { return _sender; }

    webrtc::RtpParameters GetParameters();

    // Where the negotiated codecs come from when libwebrtc reports none, as it does while not sending (receiving):
    // the connection reads them from its description
    void SetNegotiatedCodecs(std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs);

    // Collects the stats of the sender (receiver), which the connection does
    using StatsGetter = std::function<void(std::function<void(std::string)>, std::function<void(RTCCallbackException)>)>;

    void SetStatsGetter(StatsGetter getStats);

    void GetStats(std::function<void(std::string)> &, std::function<void(RTCCallbackException)> &);

    // whether the connection of the sender is closed
    void SetConnectionClosed(std::function<bool()> connectionClosed);

    // the connection of the sender, while it lives (replaceTrack chains an operation on it)
    void SetConnection(std::function<std::shared_ptr<RTCPeerConnection>()> connection);

    std::shared_ptr<RTCPeerConnection> GetConnection();

    // the transceiver of the sender, set by the connection
    void SetTransceiver(std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver);

    // null for a video sender
    std::shared_ptr<RTCDTMFSender> GetDtmf();

    void SetParameters(std::function<void()> &, std::function<void(RTCCallbackException)> &,
                       const webrtc::RtpParameters &);

    // false if the track can't be used, like one of another kind
    bool ReplaceTrack(std::optional<std::reference_wrapper<MediaStreamTrack>> track);

    void SetStreams(const std::vector<std::string> &streamIds);

    std::vector<std::string> GetStreamIds();

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

    // The parameters getParameters returned last, which setParameters takes until they expire (Python expires them
    // once the task that got them ends, as the specification requires)
    std::optional<webrtc::RtpParameters> GetLastParameters();

    // the last parameters, or only the ones with this transaction id
    void ExpireParameters(const std::optional<std::string> &transactionId);

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpSenderInterface> _sender;

    // the sender owns wrappers of its current track and transport
    std::mutex _mutex;
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<RTCDtlsTransport> _transport;
    std::function<std::vector<webrtc::RtpCodecParameters>()> _negotiatedCodecs;
    StatsGetter _getStats;
    std::function<bool()> _connectionClosed;
    std::function<std::shared_ptr<RTCPeerConnection>()> _connection;
    std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> _transceiver;
    std::shared_ptr<RTCDTMFSender> _dtmf;
    std::optional<webrtc::RtpParameters> _lastParameters;
  };

} // namespace python_webrtc
