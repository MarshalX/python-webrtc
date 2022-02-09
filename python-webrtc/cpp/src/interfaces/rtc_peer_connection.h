//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <webrtc/api/peer_connection_interface.h>
#include <webrtc/api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/functional.h>

#include "../models/python_webrtc/rtc_session_description.h"

#include "media_stream_track.h"
#include "media_stream.h"
#include "rtc_rtp_sender.h"

namespace webrtc {
  struct PeerConnectionDependencies;
}

namespace python_webrtc {

  class PeerConnectionFactory;

  class RTCPeerConnection : public webrtc::PeerConnectionObserver {
  public:
    explicit RTCPeerConnection();

    ~RTCPeerConnection() override;

    void CreateOffer(std::function<void(RTCSessionDescription)> &);

    void CreateAnswer(std::function<void(RTCSessionDescription)> &);

    void SetLocalDescription(std::function<void()> &, RTCSessionDescription &);

    void SetRemoteDescription(std::function<void()> &, RTCSessionDescription &);

    RTCRtpSender *AddTrack(MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>);

    RTCRtpSender *AddTrack(MediaStreamTrack &, const std::vector<MediaStream *> &);

    static void Init(pybind11::module &m);

    void SaveLastSdp(const RTCSessionDescriptionInit &lastSdp);

    void Close();

    // PeerConnectionObserver implementation.
    void OnSignalingChange(webrtc::PeerConnectionInterface::SignalingState new_state) override;

    void OnIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) override;

    void OnIceGatheringChange(webrtc::PeerConnectionInterface::IceGatheringState new_state) override;

    void OnIceCandidate(const webrtc::IceCandidateInterface *candidate) override;

    void OnIceCandidateError(const std::string &host_candidate, const std::string &url, int error_code,
                             const std::string &error_text) override;

    void OnRenegotiationNeeded() override;

    void OnDataChannel(rtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) override;

    void OnAddStream(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnRemoveStream(rtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnAddTrack(rtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                    const std::vector<rtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) override;

    void OnTrack(rtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;

  private:
//    someStructWith2FieldMinAndMax _port_range;
    rtc::scoped_refptr<webrtc::PeerConnectionInterface> _jinglePeerConnection;

    RTCSessionDescriptionInit _lastSdp;

    PeerConnectionFactory *_factory;
    bool _shouldReleaseFactory;
  };

}
