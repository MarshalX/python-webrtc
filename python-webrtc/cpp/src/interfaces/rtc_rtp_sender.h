//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <webrtc/api/rtp_sender_interface.h>
#include <webrtc/api/scoped_refptr.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "peer_connection_factory.h"
#include "media_stream_track.h"

namespace python_webrtc {

  class RTCRtpSender {
  public:
    explicit RTCRtpSender(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpSenderInterface>);

    static RTCRtpSender *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::RtpSenderInterface>);

    ~RTCRtpSender();

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCRtpSender *, rtc::scoped_refptr<webrtc::RtpSenderInterface>, PeerConnectionFactory *
    > *holder();

    std::optional<MediaStreamTrack *> GetTrack();

//    TODO
//    void GetTransport();
//    void GetRtcpTransport();

//    void ReplaceTrack();
//
//    void SetStreams();

    rtc::scoped_refptr<webrtc::RtpSenderInterface> sender() { return _sender; }

  private:
    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::RtpSenderInterface> _sender;
  };

} // namespace python_webrtc
