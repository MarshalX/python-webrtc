//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <api/data_channel_interface.h>

#include <pybind11/pybind11.h>

#include "../enums/enums.h"
#include "../utils/alive_guard.h"
#include "../utils/instance_holder.h"
#include "../utils/listeners.h"
#include "../utils/locked_function.h"
#include "../utils/surfaced.h"
#include "peer_connection_factory.h"

namespace python_webrtc {

  // A received message, converted to str or bytes by Python
  struct DataChannelMessage {
    std::string data;
    bool binary;
  };

  class RTCDataChannel : public webrtc::DataChannelObserver, public Listeners, public SingleObserverSlot {
  public:
    using DataState = webrtc::DataChannelInterface::DataState;

    // Starts holding its events (see Listeners::Hold), Python releases them once it has the channel
    RTCDataChannel(std::shared_ptr<PeerConnectionFactory> factory,
                   webrtc::scoped_refptr<webrtc::DataChannelInterface> channel);

    ~RTCDataChannel() override;

    RTCDataChannel(const RTCDataChannel &) = delete;
    RTCDataChannel &operator=(const RTCDataChannel &) = delete;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCDataChannel, webrtc::DataChannelInterface> &holder();

    webrtc::scoped_refptr<webrtc::DataChannelInterface> channel() { return _channel; }

    // DataChannelObserver, called on the signaling thread
    void OnStateChange() override;

    void OnMessage(const webrtc::DataBuffer &buffer) override;

    void OnBufferedAmountChange(uint64_t sentDataSize) override;

    void OnAnnounced();

    // a connection being closed fires no events of its channels
    void OnPeerConnectionClosed();

    // the largest message the remote peer takes, from the SCTP transport of the connection
    void SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter);

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

    uint64_t GetBufferedAmount();

    uint64_t GetBufferedAmountLowThreshold();

    void SetBufferedAmountLowThreshold(uint64_t threshold);

    // what binary messages are delivered as: "arraybuffer" or "blob"
    std::string GetBinaryType();

    void SetBinaryType(const std::string &binaryType);

    // whether bufferedAmount dropped to the threshold
    bool DecreaseBufferedAmount(uint64_t sent);

    void Send(const std::string &data, bool binary);

    void Close();

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DataChannelInterface> _channel;

    std::atomic<uint64_t> _bufferedAmountLowThreshold{0};
    // binaryType is "blob" rather than "arraybuffer"
    std::atomic<bool> _binaryTypeBlob{false};
    // bytes passed to send() and not reported sent yet, as Python sees it: it grows in send()
    // and drops when the event of sent bytes is delivered (see DecreaseBufferedAmount)
    std::atomic<uint64_t> _bufferedAmount{0};
    // on the signaling thread
    DataState _lastState = DataState::kConnecting;

    Surfaced<DataState> _surfacedState;
    // closing locally sets the state to closing right away, without a closing event; guards the state changes
    // that depend on it
    std::mutex _closeMutex;
    bool _closeRequested = false;

    LockedFunction<std::optional<double>()> _maxMessageSizeGetter;

    // see AliveGuard
    AliveGuard _alive;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_DATA_CHANNEL_H_
