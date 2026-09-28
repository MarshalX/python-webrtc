//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>

#include <api/rtp_receiver_interface.h>
#include <api/scoped_refptr.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"
#include "rtc_dtls_transport.h"
#include "../exceptions.h"
#include "../utils/alive_guard.h"

namespace python_webrtc {

  class RTCRtpReceiver : public webrtc::RtpReceiverObserverInterface, public SingleObserverSlot {
  public:
    explicit RTCRtpReceiver(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::RtpReceiverInterface>);

    ~RTCRtpReceiver() override;

    // RtpReceiverObserverInterface: media arrived, which unmutes the track
    void OnFirstPacketReceived(webrtc::MediaType media_type) override;

    void OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType media_type) override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCRtpReceiver, webrtc::RtpReceiverInterface> &holder();

    std::shared_ptr<MediaStreamTrack> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver() { return _receiver; }

    webrtc::RtpParameters GetParameters();

    // milliseconds of media the receiver buffers, null for the default
    std::optional<double> GetJitterBufferTarget();

    void SetJitterBufferTarget(std::optional<double> target);

    // Where the negotiated codecs come from when libwebrtc reports none, as it does while not sending (receiving):
    // the connection reads them from its description
    void SetNegotiatedCodecs(std::function<std::vector<webrtc::RtpCodecParameters>()> negotiatedCodecs);

    // the header extensions of the local description, when libwebrtc's parameters have none (like for simulcast)
    void SetNegotiatedHeaderExtensions(std::function<std::vector<webrtc::RtpExtension>()> negotiatedHeaderExtensions);

    // Collects the stats of the sender (receiver), which the connection does
    using StatsGetter = std::function<void(std::function<void(std::string)>, std::function<void(RTCCallbackException)>)>;

    void SetStatsGetter(StatsGetter getStats);

    void GetStats(std::function<void(std::string)> &, std::function<void(RTCCallbackException)> &);

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> _receiver;

    // the receiver owns wrappers of its track and current transport
    std::mutex _mutex;
    std::shared_ptr<MediaStreamTrack> _track;
    std::shared_ptr<RTCDtlsTransport> _transport;
    std::function<std::vector<webrtc::RtpCodecParameters>()> _negotiatedCodecs;
    std::function<std::vector<webrtc::RtpExtension>()> _negotiatedHeaderExtensions;
    std::optional<double> _jitterBufferTarget;
    StatsGetter _getStats;

    // the observer registration posted by the constructor
    AliveGuard _alive;
  };

} // namespace python_webrtc
