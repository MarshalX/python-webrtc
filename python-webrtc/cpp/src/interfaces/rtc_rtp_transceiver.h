//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_RTP_TRANSCEIVER_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_RTP_TRANSCEIVER_H_

#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <api/rtp_transceiver_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>

#include "../enums/enums.h"
#include "peer_connection_factory.h"
#include "rtc_rtp_receiver.h"
#include "rtc_rtp_sender.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpTransceiver {
  public:
    RTCRtpTransceiver(std::shared_ptr<PeerConnectionFactory> factory,
                      webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> &holder();

    // the connection of the transceiver, where stop() fails once it's closed; set by the connection
    void SetConnection(std::weak_ptr<RTCPeerConnection> connection);

    std::optional<std::string> GetMid();

    std::shared_ptr<RTCRtpSender> GetSender();

    std::shared_ptr<RTCRtpReceiver> GetReceiver();

    webrtc::MediaType GetKind();

    bool GetStopped();

    bool GetStopping();

    webrtc::RtpTransceiverDirection GetDirection();

    void SetDirection(webrtc::RtpTransceiverDirection direction);

    std::optional<webrtc::RtpTransceiverDirection> GetCurrentDirection();

    void Stop();

    // libwebrtc takes the codecs as a mutable view
    void SetCodecPreferences(std::vector<webrtc::RtpCodecCapability> codecs);

    std::vector<webrtc::RtpCodecCapability> GetCodecPreferences();

    std::vector<webrtc::RtpHeaderExtensionCapability> GetHeaderExtensionsToNegotiate();

    void SetHeaderExtensionsToNegotiate(const std::vector<webrtc::RtpHeaderExtensionCapability> &extensions);

    std::vector<webrtc::RtpHeaderExtensionCapability> GetNegotiatedHeaderExtensions();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> _transceiver;

    // a transceiver pairs the same sender and receiver for its whole life
    std::shared_ptr<RTCRtpSender> _sender;
    std::shared_ptr<RTCRtpReceiver> _receiver;

    std::mutex _mutex;
    std::weak_ptr<RTCPeerConnection> _connection;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_RTP_TRANSCEIVER_H_
