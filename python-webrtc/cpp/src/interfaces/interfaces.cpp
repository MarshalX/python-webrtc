//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "interfaces.h"

#include "../media/encoded_frame.h"
#include "../media/frame_transformer_bridge.h"
#include "../media/media_stream_track_processor.h"
#include "../media/rtc_rtp_script_transform.h"
#include "../media/sframe_transform.h"
#include "../media/track_generator.h"
#include "../media/video_frame_buffer.h"
#include "../utils/gil.h"
#include "../utils/native_object.h"
#include "media_stream.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"
#include "rtc_data_channel.h"
#include "rtc_dtls_transport.h"
#include "rtc_dtmf_sender.h"
#include "rtc_ice_transport.h"
#include "rtc_peer_connection/rtc_peer_connection.h"
#include "rtc_rtp_receiver.h"
#include "rtc_rtp_sender.h"
#include "rtc_rtp_transceiver.h"
#include "rtc_sctp_transport.h"

#include <map>
#include <string>

#include <pybind11/stl.h>

namespace python_webrtc {

  void Interfaces::Init(pybind11::module &m) {
    PeerConnectionFactory::Init(m);
    MediaStreamTrack::Init(m);
    MediaStream::Init(m);
    RTCIceTransport::Init(m);
    RTCDtlsTransport::Init(m);
    RTCSctpTransport::Init(m);
    RTCDTMFSender::Init(m);
    RTCRtpSender::Init(m);
    RTCRtpReceiver::Init(m);
    RTCRtpTransceiver::Init(m);
    RTCDataChannel::Init(m);
    RTCPeerConnection::Init(m);

    // the native objects alive, by type, so tests can check that none leaks
    m.def(
        "_alive",
        []() {
          auto counts = AliveCounts();
          std::map<std::string, int> alive;
          for (const char *name : {RTCPeerConnection::kName, MediaStreamTrack::kName, MediaStream::kName,
                                   RTCRtpTransceiver::kName, RTCRtpSender::kName, RTCRtpReceiver::kName,
                                   RTCDTMFSender::kName, RTCDataChannel::kName, RTCSctpTransport::kName,
                                   RTCDtlsTransport::kName, RTCIceTransport::kName, MediaStreamTrackProcessor::kName,
                                   TrackGenerator::kName, VideoFrameBuffer::kName, RTCRtpScriptTransform::kName,
                                   SFrameTransform::kName, EncodedFrame::kName, FrameTransformerBridge::kName}) {
            alive[name] = counts[name];
          }
          return alive;
        },
        nogil());
  }
} // namespace python_webrtc
