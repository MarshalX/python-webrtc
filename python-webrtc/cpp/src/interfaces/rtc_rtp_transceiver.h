//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <optional>

#include <api/scoped_refptr.h>
#include <api/rtp_transceiver_interface.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_receiver.h"

namespace python_webrtc {

  class RTCRtpTransceiver {
  public:
    RTCRtpTransceiver(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>);

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> &holder();

    std::optional<std::string> GetMid();

    std::shared_ptr<RTCRtpSender> GetSender();

    std::shared_ptr<RTCRtpReceiver> GetReceiver();

    bool GetStopped();

    webrtc::RtpTransceiverDirection GetDirection();

    void SetDirection(webrtc::RtpTransceiverDirection);

    std::optional<webrtc::RtpTransceiverDirection> GetCurrentDirection();

    void Stop();

    // whether its connection is closed, where stop() fails
    void SetConnectionClosed(std::function<bool()> connectionClosed);

    void SetCodecPreferences(const std::vector<webrtc::RtpCodecCapability> &codecs);

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
    std::function<bool()> _connectionClosed;
  };

} // namespace python_webrtc
