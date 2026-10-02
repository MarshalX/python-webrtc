//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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
#include "../utils/alive_count.h"
#include "../utils/gil.h"
#include "media_stream.h"
#include "media_stream_track.h"
#include "peer_connection_factory.h"
#include "rtc_data_channel.h"
#include "rtc_dtls_transport.h"
#include "rtc_dtmf_sender.h"
#include "rtc_ice_transport.h"
#include "rtc_peer_connection.h"
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
          return std::map<std::string, int>{
              {"RTCPeerConnection", AliveCount<RTCPeerConnection>::count.load()},
              {"MediaStreamTrack", MediaStreamTrack::holder().Alive()},
              {"MediaStream", MediaStream::holder().Alive()},
              {"RTCRtpTransceiver", RTCRtpTransceiver::holder().Alive()},
              {"RTCRtpSender", RTCRtpSender::holder().Alive()},
              {"RTCRtpReceiver", RTCRtpReceiver::holder().Alive()},
              {"RTCDTMFSender", RTCDTMFSender::holder().Alive()},
              {"RTCDataChannel", RTCDataChannel::holder().Alive()},
              {"RTCSctpTransport", RTCSctpTransport::holder().Alive()},
              {"RTCDtlsTransport", RTCDtlsTransport::holder().Alive()},
              {"RTCIceTransport", RTCIceTransport::holder().Alive()},
              {"MediaStreamTrackProcessor", AliveCount<MediaStreamTrackProcessor>::count.load()},
              {"TrackGenerator", AliveCount<TrackGenerator>::count.load()},
              {"VideoFrameBuffer", AliveCount<VideoFrameBuffer>::count.load()},
              {"RTCRtpScriptTransform", AliveCount<RTCRtpScriptTransform>::count.load()},
              {"SFrameTransform", AliveCount<SFrameTransform>::count.load()},
              {"RTCEncodedFrame", AliveCount<EncodedFrame>::count.load()},
              {"FrameTransformerBridge", AliveCount<FrameTransformerBridge>::count.load()},
          };
        },
        nogil());
  }
} // namespace python_webrtc
