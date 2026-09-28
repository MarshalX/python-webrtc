//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <functional>
#include <memory>
#include <string>

#include <api/dtmf_sender_interface.h>
#include <api/rtp_transceiver_interface.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../utils/alive_guard.h"
#include "../utils/listeners.h"

namespace python_webrtc {

  // Sends DTMF tones on an audio sender (webrtc.RTCDTMFSender)
  class RTCDTMFSender : public webrtc::DtmfSenderObserverInterface, public Listeners, public SingleObserverSlot {
  public:
    RTCDTMFSender(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::DtmfSenderInterface>);

    ~RTCDTMFSender() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCDTMFSender, webrtc::DtmfSenderInterface> &holder();

    // the transceiver of the sender, which tells whether tones can be sent; set by the sender
    void SetTransceiver(std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver);

    // DtmfSenderObserverInterface, on the signaling thread
    void OnToneChange(const std::string &tone, const std::string &tone_buffer) override;

    void InsertDtmf(const std::string &tones, int duration, int interToneGap);

    // the tones not played yet, as Python sees them: set by insertDTMF(), shortened along with tonechange events
    std::string GetToneBuffer();

    void SurfaceBuffer(const std::string &buffer, uint64_t insertion);

    bool GetCanInsertDtmf();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DtmfSenderInterface> _dtmf;
    std::mutex _mutex;
    std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> _transceiver;

    // the observer registration posted by the constructor
    AliveGuard _alive;

    std::mutex _bufferMutex;
    std::optional<std::string> _surfacedBuffer;
    uint64_t _insertions = 0;
  };

} // namespace python_webrtc
