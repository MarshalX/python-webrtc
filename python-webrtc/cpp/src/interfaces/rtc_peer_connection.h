//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>
#include <unordered_map>

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

  class RTCPeerConnection
      : public webrtc::PeerConnectionObserver, public std::enable_shared_from_this<RTCPeerConnection> {
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

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &, std::optional<std::reference_wrapper<MediaStream>>);

    std::shared_ptr<RTCRtpSender> AddTrack(MediaStreamTrack &, const std::vector<MediaStream *> &);

    std::shared_ptr<RTCRtpTransceiver> AddTransceiver(
        webrtc::MediaType, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    std::shared_ptr<RTCRtpTransceiver> AddTransceiver(
        MediaStreamTrack &, std::optional<std::reference_wrapper<webrtc::RtpTransceiverInit>> &);

    std::vector<std::shared_ptr<RTCRtpTransceiver>> GetTransceivers();

    std::vector<std::shared_ptr<RTCRtpSender>> GetSenders();

    std::vector<std::shared_ptr<RTCRtpReceiver>> GetReceivers();

    std::optional<std::shared_ptr<RTCSctpTransport>> GetSctp();

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

    template<typename T, typename U>
    using Wrappers = std::unordered_map<U *, std::shared_ptr<T>>;

    // the wrapper of a libwebrtc object of this connection, which the connection keeps while it's open
    template<typename T, typename U>
    std::shared_ptr<T> Wrap(Wrappers<T, U> &, webrtc::scoped_refptr<U>);

    // wrappers of the current objects of this connection; wrappers of the objects that are gone are released
    template<typename T, typename U>
    std::vector<std::shared_ptr<T>> Sync(Wrappers<T, U> &, const std::vector<webrtc::scoped_refptr<U>> &);

    void ReleaseWrappers();

    // declared first to be destroyed last, everything else is bound to its threads
    std::shared_ptr<PeerConnectionFactory> _factory;

    std::mutex _connectionMutex;

//    someStructWith2FieldMinAndMax _port_range;
    webrtc::scoped_refptr<webrtc::PeerConnectionInterface> _jinglePeerConnection;

    RTCSessionDescriptionInit _lastSdp;

    std::mutex _wrappersMutex;
    Wrappers<RTCRtpTransceiver, webrtc::RtpTransceiverInterface> _transceivers;
    Wrappers<RTCRtpSender, webrtc::RtpSenderInterface> _senders;
    Wrappers<RTCRtpReceiver, webrtc::RtpReceiverInterface> _receivers;
    std::shared_ptr<RTCSctpTransport> _sctp;
  };

}
