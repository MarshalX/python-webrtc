//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_RTP_SENDER_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_RTP_SENDER_H_

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <api/rtp_sender_interface.h>
#include <api/scoped_refptr.h>

#include "../enums/enums.h"
#include "../exceptions.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"
#include "rtc_dtls_transport.h"
#include "rtc_dtmf_sender.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpSender {
  public:
    explicit RTCRtpSender(std::shared_ptr<PeerConnectionFactory> factory,
                          webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpSender, webrtc::RtpSenderInterface> &holder();

    webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender() { return _sender; }

    // the connection of the sender, which knows what was negotiated for it; set by the connection
    void SetConnection(std::weak_ptr<RTCPeerConnection> connection);

    // while it lives (replaceTrack chains an operation on it)
    std::shared_ptr<RTCPeerConnection> GetConnection();

    std::optional<std::shared_ptr<MediaStreamTrack>> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::MediaType GetKind();

    // null for a video sender
    std::shared_ptr<RTCDTMFSender> GetDtmf();

    webrtc::RtpParameters GetParameters();

    void SetParameters(std::function<void()> &onSuccess, std::function<void(RTCCallbackException)> &onFailure,
                       const webrtc::RtpParameters &parameters);

    // The parameters getParameters returned last, which setParameters takes until they expire (Python expires them
    // once the task that got them ends, as the specification requires)
    std::optional<webrtc::RtpParameters> GetLastParameters();

    // the last parameters, or only the ones with this transaction id
    void ExpireParameters(const std::optional<std::string> &transactionId);

    // false if the track can't be used, like one of another kind
    bool ReplaceTrack(std::optional<std::reference_wrapper<MediaStreamTrack>> track);

    void SetStreams(const std::vector<std::string> &streamIds);

    std::vector<std::string> GetStreamIds();

    void GetStats(std::function<void(std::string)> &onSuccess, std::function<void(RTCCallbackException)> &onFailure);

    // whether its transceiver is stopping or stopped (or gone), where the sender can't be changed anymore
    bool IsTransceiverStopped();

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

  private:
    // what the DTMF sender finds the transceiver of the sender with
    std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> TransceiverGetter();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpSenderInterface> _sender;

    std::mutex _mutex;
    std::weak_ptr<RTCPeerConnection> _connection;
    // the sender owns wrappers of its current track, transport and DTMF sender
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<RTCDtlsTransport> _transport;
    std::shared_ptr<RTCDTMFSender> _dtmf;
    std::optional<webrtc::RtpParameters> _lastParameters;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_RTP_SENDER_H_
