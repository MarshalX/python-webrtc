//
// Created by Il'ya Semyonov on 1/5/22.
//

#pragma once

#include <webrtc/api/peer_connection_interface.h>
#include <webrtc/api/scoped_refptr.h>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  class PeerConnectionFactory;

  class RTCPeerConnection : public webrtc::PeerConnectionObserver {
  public:
    explicit RTCPeerConnection();

    ~RTCPeerConnection();

    static void Init(pybind11::module &m);

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

    PeerConnectionFactory *_factory;
    bool _shouldReleaseFactory;
  };

}
