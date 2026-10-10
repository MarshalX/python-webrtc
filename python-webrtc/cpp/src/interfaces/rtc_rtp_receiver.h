//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_RTP_RECEIVER_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_RTP_RECEIVER_H_

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

#include <api/rtp_receiver_interface.h>
#include <api/scoped_refptr.h>

#include "../exceptions.h"
#include "../media/frame_transformer_bridge.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"
#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCPeerConnection;

  class RTCRtpReceiver : public webrtc::RtpReceiverObserverInterface, public NativeObject<RTCRtpReceiver> {
  public:
    static constexpr const char *kName = "RTCRtpReceiver";

    // (is a synchronization source, source, timestamp in ms since the Unix epoch, RTP timestamp,
    // audio level in -dBov)
    using Source = std::tuple<bool, uint32_t, double, uint32_t, std::optional<int>>;

    explicit RTCRtpReceiver(std::shared_ptr<PeerConnectionFactory> factory,
                            webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver);

    ~RTCRtpReceiver() override;

    RTCRtpReceiver(const RTCRtpReceiver &) = delete;
    RTCRtpReceiver &operator=(const RTCRtpReceiver &) = delete;

    static void Init(pybind11::module &m);

    static Registry<RTCRtpReceiver, webrtc::RtpReceiverInterface> &registry();

    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> receiver() { return _receiver; }

    // RtpReceiverObserverInterface: media arrived, which unmutes the track
    void OnFirstPacketReceived(webrtc::MediaType mediaType) override;

    void OnFirstPacketReceivedAfterReceptiveChange(webrtc::MediaType mediaType) override;

    // the connection of the receiver, which knows what was negotiated for it; set by the connection
    void SetConnection(std::weak_ptr<RTCPeerConnection> connection);

    std::shared_ptr<MediaStreamTrack> GetTrack();

    std::optional<std::shared_ptr<RTCDtlsTransport>> GetTransport();

    webrtc::RtpParameters GetParameters();

    // milliseconds of media the receiver buffers, null for the default
    std::optional<double> GetJitterBufferTarget();

    void SetJitterBufferTarget(std::optional<double> target);

    void GetStats(std::shared_ptr<Mailbox> mailbox, uint64_t token);

    // the sources of the packets of the last 10 seconds, the most recent first
    std::vector<Source> GetSources();

    static std::optional<webrtc::RtpCapabilities> GetCapabilities(const std::string &kind);

    std::shared_ptr<RtpTransform> GetTransform() { return _transform.Get(); }

    void SetTransform(const std::shared_ptr<RtpTransform> &transform);

    void ReleaseTransform() { _transform.Release(); }

  private:
    std::shared_ptr<RTCPeerConnection> GetConnection();

    FrameSource TransformSource();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::RtpReceiverInterface> _receiver;
    // a receiver has the same (remote) track for its whole life
    const std::shared_ptr<MediaStreamTrack> _track;

    std::mutex _mutex;
    std::weak_ptr<RTCPeerConnection> _connection;
    // the receiver owns the wrapper of its current transport
    std::shared_ptr<RTCDtlsTransport> _transport;
    std::optional<double> _jitterBufferTarget;
    TransformSlot _transform;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_RTP_RECEIVER_H_
