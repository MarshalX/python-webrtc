//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_data_channel.h"

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCDataChannel::RTCDataChannel(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::DataChannelInterface> channel)
      : _factory(std::move(factory)), _channel(std::move(channel)) {
    Hold();
    // open only once the open event is delivered
    _surfacedState.Surface(DataState::kConnecting);
    // see AliveGuard
    _factory->_signalingThread->PostTask(_alive.Guard([this]() {
      _lastState = _channel->state();
      if (_lastState != DataState::kOpen && _lastState != DataState::kConnecting) {
        _surfacedState.Surface(_lastState);
      }
      // messages received meanwhile are delivered to the observer once it's registered, and are held too
      _channel->RegisterObserver(this);
      // a channel announced by the remote peer is open already, but its open event follows the datachannel one
      if (_lastState == DataState::kOpen) {
        Emit("open", _lastState);
      }
    }));
  }

  RTCDataChannel::~RTCDataChannel() {
    gil_release_if_held release;

    // the channel has a single observer slot, a newer wrapper of it may have taken it over already
    auto replaced = holder().HasLive(_channel.get());
    // callbacks run on the signaling thread, so after this none of them can be running or start again
    _factory->_signalingThread->BlockingCall([this, replaced]() {
      if (!replaced) {
        _channel->UnregisterObserver();
      }
    });
    _channel = nullptr;
    DropListeners();
  }

  void RTCDataChannel::Init(pybind11::module &m) {
    pybind11::class_<DataChannelMessage>(m, "DataChannelMessage")
        .def_property_readonly("data", [](const DataChannelMessage &message) -> pybind11::object {
          if (message.binary) {
            return pybind11::bytes(message.data);
          }
          // the upper layers verify UTF-8, as libwebrtc doesn't
          return pybind11::reinterpret_steal<pybind11::object>(
              PyUnicode_DecodeUTF8(message.data.data(), static_cast<Py_ssize_t>(message.data.size()), "replace"));
        });

    Listeners::BindClass<RTCDataChannel>(m, "RTCDataChannel")
        .def_property_readonly("label", nogil_fn(&RTCDataChannel::GetLabel))
        .def_property_readonly("ordered", nogil_fn(&RTCDataChannel::GetOrdered))
        .def_property_readonly("maxPacketLifeTime", nogil_fn(&RTCDataChannel::GetMaxPacketLifeTime))
        .def_property_readonly("maxRetransmits", nogil_fn(&RTCDataChannel::GetMaxRetransmits))
        .def_property_readonly("protocol", nogil_fn(&RTCDataChannel::GetProtocol))
        .def_property_readonly("negotiated", nogil_fn(&RTCDataChannel::GetNegotiated))
        .def_property_readonly("id", nogil_fn(&RTCDataChannel::GetId))
        .def_property_readonly("priority", nogil_fn(&RTCDataChannel::GetPriority))
        .def_property_readonly("readyState", nogil_fn(&RTCDataChannel::GetReadyState))
        .def_property_readonly("bufferedAmount", nogil_fn(&RTCDataChannel::GetBufferedAmount))
        .def_property("bufferedAmountLowThreshold", nogil_fn(&RTCDataChannel::GetBufferedAmountLowThreshold),
                      nogil_fn(&RTCDataChannel::SetBufferedAmountLowThreshold))
        .def_property("binaryType", nogil_fn(&RTCDataChannel::GetBinaryType), nogil_fn(&RTCDataChannel::SetBinaryType))
        .def("send", &RTCDataChannel::Send, nogil(), pybind11::arg("data"), pybind11::arg("binary"))
        .def("close", &RTCDataChannel::Close, nogil())
        .def("_surfaceState", &RTCDataChannel::SurfaceState, nogil(), pybind11::arg("state"))
        .def("_decreaseBufferedAmount", &RTCDataChannel::DecreaseBufferedAmount, nogil(), pybind11::arg("sent"))
        .def("_release", &RTCDataChannel::Release);
  }

  InstanceHolder<RTCDataChannel, webrtc::DataChannelInterface> &RTCDataChannel::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCDataChannel, webrtc::DataChannelInterface>();
    return *holder;
  }

  void RTCDataChannel::OnStateChange() {
    auto state = _channel->state();
    if (state == _lastState) {
      return;
    }
    auto previous = _lastState;
    _lastState = state;

    {
      std::lock_guard<std::mutex> lock(_closeMutex);
      if (_closeRequested && state == DataState::kClosing) {
        // closing locally has shown the closing state already, and fires no event
        return;
      }
      _surfacedState.Changed(IsTracked(), previous);
    }

    switch (state) {
      case DataState::kOpen:
        Emit("open", state);
        break;
      case DataState::kClosing:
        Emit("closing", state);
        break;
      case DataState::kClosed: {
        auto error = _channel->error();
        // closing locally isn't an error, even if queued messages couldn't be sent
        bool closedLocally;
        {
          std::lock_guard<std::mutex> lock(_closeMutex);
          closedLocally = _closeRequested;
        }
        if (!error.ok() && !closedLocally) {
          Emit("error", RTCCallbackException(std::move(error)));
        }
        Emit("close", state);
        break;
      }
      default:
        break;
    }
  }

  void RTCDataChannel::OnMessage(const webrtc::DataBuffer &buffer) {
    Emit("message", DataChannelMessage{std::string(buffer.data.cdata<char>(), buffer.size()), buffer.binary});
  }

  void RTCDataChannel::OnBufferedAmountChange(uint64_t sentDataSize) {
    // an internal event: Python decreases bufferedAmount when it's delivered
    Emit("_sent", sentDataSize);
  }

  void RTCDataChannel::OnAnnounced() {
    std::lock_guard<std::mutex> lock(_closeMutex);
    // a channel announced by the remote peer is open when its datachannel event fires
    if (_lastState == DataState::kConnecting || _lastState == DataState::kOpen) {
      _surfacedState.Surface(DataState::kOpen);
    }
  }

  void RTCDataChannel::OnPeerConnectionClosed() {
    Mute();
    _surfacedState.Reset();
  }

  void RTCDataChannel::SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter) {
    _maxMessageSizeGetter.Set(std::move(getter));
  }

  std::string RTCDataChannel::GetLabel() {
    return _channel->label();
  }

  bool RTCDataChannel::GetOrdered() {
    return _channel->ordered();
  }

  std::optional<int> RTCDataChannel::GetMaxPacketLifeTime() {
    return _channel->maxPacketLifeTime();
  }

  std::optional<int> RTCDataChannel::GetMaxRetransmits() {
    return _channel->maxRetransmitsOpt();
  }

  std::string RTCDataChannel::GetProtocol() {
    return _channel->protocol();
  }

  bool RTCDataChannel::GetNegotiated() {
    return _channel->negotiated();
  }

  std::optional<int> RTCDataChannel::GetId() {
    auto id = _channel->id();
    if (id < 0) {
      return std::nullopt;
    }
    return id;
  }

  webrtc::Priority RTCDataChannel::GetPriority() {
    // the ranges Chromium maps priority values to
    auto value = _channel->priority().value();
    if (value <= 192) {
      return webrtc::Priority::kVeryLow;
    }
    if (value <= 384) {
      return webrtc::Priority::kLow;
    }
    if (value <= 768) {
      return webrtc::Priority::kMedium;
    }
    return webrtc::Priority::kHigh;
  }

  RTCDataChannel::DataState RTCDataChannel::GetReadyState() {
    return _surfacedState.Get(_channel->state());
  }

  void RTCDataChannel::SurfaceState(DataState state) {
    std::lock_guard<std::mutex> lock(_closeMutex);
    // an open event that was queued before closing locally doesn't reopen the channel
    if (_closeRequested && state == DataState::kOpen) {
      return;
    }
    _surfacedState.Surface(state);
  }

  uint64_t RTCDataChannel::GetBufferedAmount() {
    return _bufferedAmount;
  }

  std::string RTCDataChannel::GetBinaryType() {
    return _binaryTypeBlob ? "blob" : "arraybuffer";
  }

  void RTCDataChannel::SetBinaryType(const std::string &binaryType) {
    // an enum attribute ignores values it doesn't have
    if (binaryType == "blob" || binaryType == "arraybuffer") {
      _binaryTypeBlob = binaryType == "blob";
    }
  }

  uint64_t RTCDataChannel::GetBufferedAmountLowThreshold() {
    return _bufferedAmountLowThreshold;
  }

  void RTCDataChannel::SetBufferedAmountLowThreshold(uint64_t threshold) {
    _bufferedAmountLowThreshold = threshold;
  }

  bool RTCDataChannel::DecreaseBufferedAmount(uint64_t sent) {
    uint64_t amount = _bufferedAmount.load();
    uint64_t decreased;
    do {
      decreased = amount > sent ? amount - sent : 0;
    } while (!_bufferedAmount.compare_exchange_weak(amount, decreased));

    auto threshold = _bufferedAmountLowThreshold.load();
    return amount > threshold && decreased <= threshold;
  }

  static RTCException sendQueueFullError() {
    return {webrtc::RTCErrorType::RESOURCE_EXHAUSTED, "The send queue of the RTCDataChannel is full"};
  }

  void RTCDataChannel::Send(const std::string &data, bool binary) {
    if (GetReadyState() != DataState::kOpen) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "RTCDataChannel.readyState is not 'open'");
    }

    auto getter = _maxMessageSizeGetter.Get();
    auto maxMessageSize = getter ? getter() : std::nullopt;
    if (maxMessageSize && static_cast<double>(data.size()) > *maxMessageSize) {
      throw pybind11::value_error("The message is larger than the maxMessageSize of the SCTP transport");
    }

    // a full queue fails the send, rather than libwebrtc closing the channel with an error
    if (_bufferedAmount + data.size() > webrtc::DataChannelInterface::MaxSendQueueSize()) {
      throw sendQueueFullError();
    }
    _bufferedAmount += data.size();
    auto sent = _channel->Send(webrtc::DataBuffer(webrtc::CopyOnWriteBuffer(data.data(), data.size()), binary));
    if (!sent && _channel->state() == DataState::kOpen) {
      _bufferedAmount -= data.size();
      throw sendQueueFullError();
    }
  }

  void RTCDataChannel::Close() {
    // read before locking: it's a call to the signaling thread, which takes the lock in OnStateChange
    auto current = _channel->state();
    {
      std::lock_guard<std::mutex> lock(_closeMutex);
      auto state = _surfacedState.Get(current);
      if (state == DataState::kClosing || state == DataState::kClosed) {
        return;
      }
      _closeRequested = true;
      _surfacedState.Surface(DataState::kClosing);
    }
    _channel->Close();
  }

} // namespace python_webrtc
