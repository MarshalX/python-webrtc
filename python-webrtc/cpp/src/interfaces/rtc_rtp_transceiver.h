//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <optional>

#include <webrtc/api/scoped_refptr.h>
#include <api/rtp_transceiver_interface.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_receiver.h"

namespace python_webrtc {

  class RTCRtpTransceiver {
  public:
    RTCRtpTransceiver(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpTransceiverInterface>);

    static RTCRtpTransceiver *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpTransceiverInterface>);

    ~RTCRtpTransceiver();

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCRtpTransceiver *, rtc::scoped_refptr<webrtc::RtpTransceiverInterface>, PeerConnectionFactory *
    > *holder();

    std::optional<std::string> GetMid();

    RTCRtpSender *GetSender();

    RTCRtpReceiver *GetReceiver();

    bool GetStopped();

    webrtc::RtpTransceiverDirection GetDirection();

    void SetDirection(webrtc::RtpTransceiverDirection);

    std::optional<webrtc::RtpTransceiverDirection> GetCurrentDirection();

    void Stop();

    // TODO bind webrtc::RtpCodecCapability
    //  void SetCodecPreferences();

  private:
    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::RtpTransceiverInterface> _transceiver;
  };

} // namespace python_webrtc
