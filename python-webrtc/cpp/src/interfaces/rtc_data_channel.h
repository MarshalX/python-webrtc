//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <memory>
#include <optional>
#include <string>

#include <api/data_channel_interface.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "../exceptions.h"
#include "../utils/instance_holder.h"
#include "../utils/alive_guard.h"
#include "../utils/listeners.h"

namespace python_webrtc {

  // A received message, converted to str or bytes by Python
  struct DataChannelMessage {
    std::string data;
    bool binary;
  };

  class RTCDataChannel : public webrtc::DataChannelObserver, public Listeners, public SingleObserverSlot {
  public:
    // Starts holding its events (see Listeners::Hold), Python releases them once it has the channel
    RTCDataChannel(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::DataChannelInterface>);

    ~RTCDataChannel() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCDataChannel, webrtc::DataChannelInterface> &holder();

    webrtc::scoped_refptr<webrtc::DataChannelInterface> channel() { return _channel; }

    // DataChannelObserver, called on the signaling thread
    void OnStateChange() override;

    void OnMessage(const webrtc::DataBuffer &buffer) override;

    void OnBufferedAmountChange(uint64_t sent_data_size) override;

    void OnAnnounced();

    // a connection being closed fires no events of its channels
    void OnPeerConnectionClosed();

    void Send(const std::string &data, bool binary);

    // the largest message the remote peer takes, from the SCTP transport of the connection
    void SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter);

    void Close();

    uint64_t GetBufferedAmount();

    uint64_t GetBufferedAmountLowThreshold();

    void SetBufferedAmountLowThreshold(uint64_t threshold);

    std::optional<int> GetId();

    // readyState as Python sees it: it changes when its event is delivered (see RTCPeerConnection::SurfaceState)
    webrtc::DataChannelInterface::DataState GetReadyState();

    void SurfaceState(int state);

    // whether bufferedAmount dropped to the threshold
    bool DecreaseBufferedAmount(uint64_t sent);

  private:
    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DataChannelInterface> _channel;

    std::atomic<uint64_t> _bufferedAmountLowThreshold{0};
    // bytes passed to send() and not reported sent yet, as Python sees it: it grows in send()
    // and drops when the event of sent bytes is delivered (see DecreaseBufferedAmount)
    std::atomic<uint64_t> _bufferedAmount{0};
    webrtc::DataChannelInterface::DataState _lastState = webrtc::DataChannelInterface::DataState::kConnecting;

    std::mutex _stateMutex;
    std::optional<webrtc::DataChannelInterface::DataState> _surfacedState;
    // closing locally sets the state to closing right away, without a closing event
    bool _closeRequested = false;

    std::mutex _getterMutex;
    std::function<std::optional<double>()> _maxMessageSizeGetter;

    // the observer registration posted by the constructor
    AliveGuard _alive;
  };

} // namespace python_webrtc
