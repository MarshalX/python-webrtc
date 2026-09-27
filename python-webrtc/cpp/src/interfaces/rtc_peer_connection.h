//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <mutex>

#include <api/peer_connection_interface.h>
#include <api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/functional.h>

#include "../exceptions.h"
#include "../models/python_webrtc/rtc_session_description.h"

#include "media_stream_track.h"
#include "media_stream.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_transceiver.h"
#include "rtc_sctp_transport.h"

namespace webrtc {
  struct PeerConnectionDependencies;
}

namespace python_webrtc {

  class PeerConnectionFactory;

  class RTCPeerConnection : public webrtc::PeerConnectionObserver {
  public:
    explicit RTCPeerConnection();

    static void Init(pybind11::module &m);

    ~RTCPeerConnection() override;

    void CreateOffer(
        std::function<void(RTCSessionDescription)> &, std::function<void(CallbackPythonWebRTCException)> &);

    void CreateAnswer(
        std::function<void(RTCSessionDescription)> &, std::function<void(CallbackPythonWebRTCException)> &);

    void SetLocalDescription(
        std::function<void()> &, std::function<void(CallbackPythonWebRTCException)> &, RTCSessionDescription &);

    void SetRemoteDescription(
        std::function<void()> &, std::function<void(CallbackPythonWebRTCException)> &, RTCSessionDescription &);

    RTCRtpSender *AddTrack(MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>);

    RTCRtpSender *AddTrack(MediaStreamTrack &, const std::vector<MediaStream *> &);

    RTCRtpTransceiver *AddTransceiver(
        webrtc::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    RTCRtpTransceiver *AddTransceiver(
        MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    std::vector<RTCRtpTransceiver *> GetTransceivers();

    std::vector<RTCRtpSender *> GetSenders();

    std::vector<RTCRtpReceiver *> GetReceivers();

    std::optional<RTCSctpTransport *> GetSctp();

    void RestartIce();

    void RemoveTrack(RTCRtpSender &);

    void SaveLastSdp(const RTCSessionDescriptionInit &lastSdp);

    void Close();

    webrtc::PeerConnectionInterface::PeerConnectionState GetConnectionState();

    webrtc::PeerConnectionInterface::SignalingState GetSignalingState();

    webrtc::PeerConnectionInterface::IceConnectionState GetIceConnectionState();

    webrtc::PeerConnectionInterface::IceGatheringState GetIceGatheringState();

    std::optional<RTCSessionDescription> GetLocalDescription();

    std::optional<RTCSessionDescription> GetRemoteDescription();

    // PeerConnectionObserver implementation.
    void OnSignalingChange(webrtc::PeerConnectionInterface::SignalingState new_state) override;

    void OnIceConnectionChange(webrtc::PeerConnectionInterface::IceConnectionState new_state) override;

    void OnIceGatheringChange(webrtc::PeerConnectionInterface::IceGatheringState new_state) override;

    void OnIceCandidate(const webrtc::IceCandidateInterface *candidate) override;

    void OnIceCandidateError(const std::string &address, int port, const std::string &url, int error_code,
                             const std::string &error_text) override;

    void OnRenegotiationNeeded() override;

    void OnDataChannel(webrtc::scoped_refptr<webrtc::DataChannelInterface> data_channel) override;

    void OnAddStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnRemoveStream(webrtc::scoped_refptr<webrtc::MediaStreamInterface> stream) override;

    void OnAddTrack(webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver,
                    const std::vector<webrtc::scoped_refptr<webrtc::MediaStreamInterface>> &streams) override;

    void OnTrack(webrtc::scoped_refptr<webrtc::RtpTransceiverInterface> transceiver) override;

  private:
    std::optional<RTCSessionDescription> GetDescription(bool local);

    // Python threads may call close() concurrently with other methods (the GIL is released)
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> connection();

    std::mutex _connectionMutex;

//    someStructWith2FieldMinAndMax _port_range;
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _jinglePeerConnection;

    RTCSessionDescriptionInit _lastSdp;

    PeerConnectionFactory *_factory;
    std::atomic<bool> _shouldReleaseFactory;
  };

}
