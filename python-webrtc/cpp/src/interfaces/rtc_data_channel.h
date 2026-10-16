//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_

#include <atomic>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>

#include <api/data_channel_interface.h>
#include <rtc_base/copy_on_write_buffer.h>

#include <pybind11/pybind11.h>

#include "../enums/enums.h"
#include "../utils/locked_function.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "../utils/surfaced.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // A received message, converted to str or bytes by Python
  struct DataChannelMessage {
    // refcounted and only read, so it's shared across threads without a copy
    webrtc::CopyOnWriteBuffer data;
    bool binary;
  };

  class RTCDataChannel : public webrtc::DataChannelObserver,
                         public NativeObject<RTCDataChannel>,
                         public Emitter<RTCDataChannel> {
  public:
    static constexpr const char *kName = "RTCDataChannel";

    using DataState = webrtc::DataChannelInterface::DataState;

    RTCDataChannel(std::shared_ptr<PeerConnectionFactory> factory,
                   webrtc::scoped_refptr<webrtc::DataChannelInterface> channel);

    ~RTCDataChannel() override;

    RTCDataChannel(const RTCDataChannel &) = delete;
    RTCDataChannel &operator=(const RTCDataChannel &) = delete;

    static void Init(pybind11::module &m);

    static Registry<RTCDataChannel, webrtc::DataChannelInterface> &registry();

    webrtc::scoped_refptr<webrtc::DataChannelInterface> channel() { return _channel; }

    // DataChannelObserver on the network thread, skipping libwebrtc's hop to the signaling thread
    bool IsOkToCallOnTheNetworkThread() override { return true; }

    void OnStateChange() override;

    void OnMessage(const webrtc::DataBuffer &buffer) override;

    void OnBufferedAmountChange(uint64_t sentDataSize) override;

    void OnAnnounced();

    // a connection being closed fires no events of its channels
    void OnPeerConnectionClosed();

    // the largest message the remote peer takes, from the SCTP transport of the connection
    void SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter);

    // on the signaling thread
    void SetClosedCallback(std::function<void()> callback);

    std::string GetLabel();

    bool GetOrdered();

    std::optional<int> GetMaxPacketLifeTime();

    std::optional<int> GetMaxRetransmits();

    std::string GetProtocol();

    bool GetNegotiated();

    std::optional<int> GetId();

    webrtc::Priority GetPriority();

    // see Surfaced
    DataState GetReadyState();

    void SurfaceState(DataState state);

    bool GetOpenDelivered();

    uint64_t GetBufferedAmount();

    uint64_t GetBufferedAmountLowThreshold();

    void SetBufferedAmountLowThreshold(uint64_t threshold);

    // what binary messages are delivered as: "arraybuffer" or "blob"
    std::string GetBinaryType();

    void SetBinaryType(const std::string &binaryType);

    // whether bufferedAmount dropped to the threshold
    bool DecreaseBufferedAmount(uint64_t sent);

    // whether the message is the only one queued: the channel's activity changes only then; data is copied
    bool Send(std::string_view data, bool binary);

    void Close();

  private:
    void SendNow(webrtc::DataBuffer buffer);

    void SetStateLocked(DataState state);

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DataChannelInterface> _channel;

    std::atomic<uint64_t> _bufferedAmountLowThreshold{0};
    // binaryType is "blob" rather than "arraybuffer"
    std::atomic<bool> _binaryTypeBlob{false};
    // bytes passed to send() and not reported sent yet, as Python sees it: it grows in send()
    // and drops when the event of sent bytes is delivered (see DecreaseBufferedAmount)
    std::atomic<uint64_t> _bufferedAmount{0};
    // under _closeMutex
    DataState _lastState = DataState::kConnecting;
    // sent before libwebrtc opens an announced channel; under _closeMutex
    std::deque<webrtc::DataBuffer> _held;

    Surfaced<DataState> _surfacedState;
    // closing locally sets the state to closing right away, without a closing event; guards the state changes
    // that depend on it
    std::mutex _closeMutex;
    bool _closeRequested = false;
    bool _openDelivered = false;

    LockedFunction<std::optional<double>()> _maxMessageSizeGetter;
    LockedFunction<void()> _closedCallback;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_
