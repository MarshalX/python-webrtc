//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

#include <api/rtp_receiver_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"
#include "../exceptions.h"
#include "../utils/alive_guard.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpReceiver : public webrtc::RtpReceiverObserverInterface, public SingleObserverSlot {
  public:
    // (is a synchronization source, source, timestamp in ms since the Unix epoch, RTP timestamp,
    // audio level in -dBov)
    using Source = std::tuple<bool, uint32_t, double, uint32_t, std::optional<int>>;

    explicit RTCRtpReceiver(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpReceiverInterface>);

    ~RTCRtpReceiver() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &holder();

    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver() { return _receiver; }

    // RtpReceiverObserverInterface: media arrived, which unmutes the track
    void OnFirstPacketReceived(webrtc::MediaType) override;

    void OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType) override;

    // the connection of the receiver, which knows what was negotiated for it; set by the connection
    void SetConnection(std::weak_ptr<RTCPeerConnection> connection);

    std::shared_ptr<MediaStreamTrack> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::RtpParameters GetParameters();

    // milliseconds of media the receiver buffers, null for the default
    std::optional<double> GetJitterBufferTarget();

    void SetJitterBufferTarget(std::optional<double> target);

    void GetStats(std::function<void(std::string)> &, std::function<void(RTCCallbackException)> &);

    // the sources of the packets of the last 10 seconds, the most recent first
    std::vector<Source> GetSources();

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

  private:
    std::shared_ptr<RTCPeerConnection> GetConnection();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> _receiver;
    // a receiver has the same (remote) track for its whole life
    const std::shared_ptr<MediaStreamTrack> _track;

    std::mutex _mutex;
    std::weak_ptr<RTCPeerConnection> _connection;
    // the receiver owns the wrapper of its current transport
    std::shared_ptr<RTCDtlsTransport> _transport;
    std::optional<double> _jitterBufferTarget;

    // see AliveGuard
    AliveGuard _alive;
  };

} // namespace python_webrtc
