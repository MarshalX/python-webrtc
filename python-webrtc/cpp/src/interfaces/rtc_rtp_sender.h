//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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
#include "../media/frame_transformer_bridge.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"
#include "rtc_dtls_transport.h"
#include "rtc_dtmf_sender.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpSender : public NativeObject<RTCRtpSender> {
  public:
    static constexpr const char *kName = "RTCRtpSender";

    explicit RTCRtpSender(std::shared_ptr<PeerConnectionFactory> factory,
                          webrtc::scoped_refptr<webrtc::RtpSenderInterface> sender);

    static void Init(pybind11::module &m);

    static Registry<RTCRtpSender, webrtc::RtpSenderInterface> &registry();

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

    void SetParameters(std::shared_ptr<Mailbox> mailbox, uint64_t token, const webrtc::RtpParameters &parameters);

    // settable until a setParameters succeeds
    std::optional<webrtc::RtpParameters> GetLastParameters();

    // the next getParameters returns new ones, if the transaction id matches (or none is given)
    void ExpireParameters(const std::optional<std::string> &transactionId);

    // setParameters needs a new getParameters
    void ClearParameters();

    // false if the track can't be used, like one of another kind
    bool ReplaceTrack(std::optional<std::reference_wrapper<MediaStreamTrack>> track);

    void SetStreams(const std::vector<std::string> &streamIds);

    std::vector<std::string> GetStreamIds();

    void GetStats(std::shared_ptr<Mailbox> mailbox, uint64_t token);

    // whether its transceiver is stopping or stopped (or gone), where the sender can't be changed anymore
    bool IsTransceiverStopped();

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

    std::shared_ptr<RtpTransform> GetTransform() { return _transform.Get(); }

    void SetTransform(const std::shared_ptr<RtpTransform> &transform);

    void ReleaseTransform() { _transform.Release(); }

  private:
    FrameSource TransformSource();

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
    bool _lastParametersExpired = false;
    TransformSlot _transform;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_RTP_SENDER_H_
