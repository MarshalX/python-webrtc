//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_DTMF_SENDER_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_DTMF_SENDER_H_

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <api/dtmf_sender_interface.h>
#include <api/rtp_transceiver_interface.h>

#include <pybind11/pybind11.h>

#include "../utils/locked_function.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // Sends DTMF tones on an audio sender (webrtc.RTCDTMFSender)
  class RTCDTMFSender : public webrtc::DtmfSenderObserverInterface,
                        public NativeObject<RTCDTMFSender>,
                        public Emitter<RTCDTMFSender> {
  public:
    static constexpr const char *kName = "RTCDTMFSender";

    RTCDTMFSender(std::shared_ptr<PeerConnectionFactory> factory,
                  webrtc::scoped_refptr<webrtc::DtmfSenderInterface> dtmf);

    ~RTCDTMFSender() override;

    RTCDTMFSender(const RTCDTMFSender &) = delete;
    RTCDTMFSender &operator=(const RTCDTMFSender &) = delete;

    static void Init(pybind11::module &m);

    static Registry<RTCDTMFSender, webrtc::DtmfSenderInterface> &registry();

    // the transceiver of the sender, which tells whether tones can be sent; set by the sender
    void SetTransceiver(std::function<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> transceiver);

    // DtmfSenderObserverInterface, on the signaling thread
    void OnToneChange(const std::string &tone, const std::string &toneBuffer) override;

    // "determine if DTMF can be sent"
    void CheckCanSend();
    void InsertDtmf(const std::string &tones, int duration, int interToneGap);

    // the tones not played yet, as Python sees them: set by insertDTMF(), shortened along with tonechange events
    std::string GetToneBuffer();

    // the buffer a delivered tonechange event left, if no insertDTMF() came after the tone; ended by the empty tone
    void SurfaceBuffer(const std::string &buffer, uint64_t insertion, bool ended);

    bool GetPlaying();

    bool GetCanInsertDtmf();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DtmfSenderInterface> _dtmf;
    LockedFunction<webrtc::scoped_refptr<webrtc::RtpTransceiverInterface>()> _transceiver;

    std::mutex _bufferMutex;
    std::optional<std::string> _surfacedBuffer;
    uint64_t _insertions = 0;
    bool _playing = false;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_DTMF_SENDER_H_
