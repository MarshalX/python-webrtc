//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_data_channel.h"

#include <utility>

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  RTCDataChannel::RTCDataChannel(std::shared_ptr<PeerConnectionFactory> factory,
                                 webrtc::scoped_refptr<webrtc::DataChannelInterface> channel)
      : _factory(std::move(factory)), _channel(std::move(channel)) {
    // open only once the open event is delivered
    _surfacedState.Surface(DataState::kConnecting);
    // after the datachannel event of an announced channel, which is emitted on the signaling thread
    _factory->signalingThread()->PostTask(Guard([this]() {
      registry().SetObserver(_channel.get(), this);
      // where the channel changes state: no change is missed between reading the state and registering
      _factory->workerThread()->PostTask(Guard([this]() {
        DataState state{};
        {
          const std::scoped_lock lock(_closeMutex);
          state = _channel->state();
          SetStateLocked(state);
          if (state != DataState::kOpen && state != DataState::kConnecting) {
            _surfacedState.Surface(state);
          }
        }
        // a channel already open (announced or negotiated) fires open once bound
        if (state == DataState::kOpen) {
          _surfacedState.Changed(IsBound(), DataState::kConnecting);
          Emit("open", state);
        }
        // delivers the messages received meanwhile, behind the open event
        _channel->RegisterObserver(this);
      }));
    }));
  }

  RTCDataChannel::~RTCDataChannel() {
    // unregistering waits for the network thread, where callbacks run: none can be running or start again
    BlockingCallOn(_factory->signalingThread(), [this]() {
      // a newer wrapper of the channel may have taken its single observer slot
      if (registry().TakeObserver(_channel.get(), this)) {
        _channel->UnregisterObserver();
      }
    });
    _channel = nullptr;
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

    DefineBinding(pybind11::class_<RTCDataChannel, Binding, std::shared_ptr<RTCDataChannel>>(m, "RTCDataChannel"))
        .def_property_readonly("_id", &RTCDataChannel::Id)
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
        .def("_decreaseBufferedAmount", &RTCDataChannel::DecreaseBufferedAmount, nogil(), pybind11::arg("sent"));
  }

  Registry<RTCDataChannel, webrtc::DataChannelInterface> &RTCDataChannel::registry() {
    static ForkLocal<Registry<RTCDataChannel, webrtc::DataChannelInterface>> registry;
    return registry.Get();
  }

  void RTCDataChannel::OnStateChange() {
    auto state = _channel->state();
    {
      const std::scoped_lock lock(_closeMutex);
      if (state == _lastState) {
        return;
      }
      auto previous = _lastState;
      SetStateLocked(state);
      if (_closeRequested && state == DataState::kClosing) {
        // closing locally has shown the closing state already, and fires no event
        return;
      }
      _surfacedState.Changed(IsBound(), previous);
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
      bool closedLocally = false;
      {
        const std::scoped_lock lock(_closeMutex);
        closedLocally = _closeRequested;
      }
      if (!error.ok() && !closedLocally) {
        Emit("error", RTCCallbackException(std::move(error)));
      }
      Emit("close", state);
      if (auto closed = _closedCallback.Get()) {
        _factory->signalingThread()->PostTask(std::move(closed));
      }
      break;
    }
    default:
      break;
    }
  }

  void RTCDataChannel::OnMessage(const webrtc::DataBuffer &buffer) {
    Emit("message",
         DataChannelMessage{.data = std::string(buffer.data.cdata<char>(), buffer.size()), .binary = buffer.binary});
  }

  void RTCDataChannel::OnBufferedAmountChange(uint64_t sentDataSize) {
    // an internal event: Python decreases bufferedAmount when it's delivered
    Emit("_sent", sentDataSize);
  }

  void RTCDataChannel::OnAnnounced() {
    const std::scoped_lock lock(_closeMutex);
    // a channel announced by the remote peer is open when its datachannel event fires
    if (_lastState == DataState::kConnecting || _lastState == DataState::kOpen) {
      _surfacedState.Surface(DataState::kOpen);
    }
  }

  void RTCDataChannel::OnPeerConnectionClosed() {
    Unbind();
    _surfacedState.Reset();
  }

  void RTCDataChannel::SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter) {
    _maxMessageSizeGetter.Set(std::move(getter));
  }

  void RTCDataChannel::SetClosedCallback(std::function<void()> callback) {
    _closedCallback.Set(std::move(callback));
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
    // splits at the midpoints between the DCEP priority values of W3C webrtc-priority (128, 256, 512, 1024)
    constexpr int veryLowMax = 192;
    constexpr int lowMax = 384;
    constexpr int mediumMax = 768;
    auto value = _channel->priority().value();
    if (value <= veryLowMax) {
      return webrtc::Priority::kVeryLow;
    }
    if (value <= lowMax) {
      return webrtc::Priority::kLow;
    }
    if (value <= mediumMax) {
      return webrtc::Priority::kMedium;
    }
    return webrtc::Priority::kHigh;
  }

  RTCDataChannel::DataState RTCDataChannel::GetReadyState() {
    return _surfacedState.ShownOr(IsBound(), [this]() { return _channel->state(); });
  }

  void RTCDataChannel::SurfaceState(DataState state) {
    const std::scoped_lock lock(_closeMutex);
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
    auto decrease = [sent](uint64_t value) { return value > sent ? value - sent : 0; };
    uint64_t amount = _bufferedAmount.load();
    uint64_t decreased = decrease(amount);
    while (!_bufferedAmount.compare_exchange_weak(amount, decreased)) {
      decreased = decrease(amount);
    }

    auto threshold = _bufferedAmountLowThreshold.load();
    return amount > threshold && decreased <= threshold;
  }

  namespace {

    RTCException sendQueueFullError() {
      return {webrtc::RTCErrorType::RESOURCE_EXHAUSTED, "The send queue of the RTCDataChannel is full"};
    }

  } // namespace

  bool RTCDataChannel::Send(const std::string &data, bool binary) {
    if (GetReadyState() != DataState::kOpen) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "RTCDataChannel.readyState is not 'open'");
    }

    auto getter = _maxMessageSizeGetter.Get();
    auto maxMessageSize = getter ? getter() : std::nullopt;
    if (maxMessageSize && static_cast<double>(data.size()) > *maxMessageSize) {
      throw pybind11::type_error("The message is larger than the maxMessageSize of the SCTP transport");
    }

    // a full queue fails the send, rather than libwebrtc closing the channel with an error
    if (_bufferedAmount + data.size() > webrtc::DataChannelInterface::MaxSendQueueSize()) {
      throw sendQueueFullError();
    }
    auto queued = _bufferedAmount.fetch_add(data.size());
    webrtc::DataBuffer buffer(webrtc::CopyOnWriteBuffer(data.data(), data.size()), binary);
    {
      const std::scoped_lock lock(_closeMutex);
      // announced, not yet opened by libwebrtc
      if (_lastState == DataState::kConnecting) {
        _held.push_back(std::move(buffer));
        return queued == 0;
      }
    }
    SendNow(std::move(buffer));
    return queued == 0;
  }

  void RTCDataChannel::SendNow(webrtc::DataBuffer buffer) {
    auto size = buffer.size();
    // posted to the network thread, in call order; a failed send closes the channel
    _channel->SendAsync(std::move(buffer), [weak = weak_from_this(), size](const webrtc::RTCError &error) {
      auto self = weak.lock();
      if (!error.ok() && self) {
        self->DecreaseBufferedAmount(size);
      }
    });
  }

  void RTCDataChannel::SetStateLocked(DataState state) {
    _lastState = state;
    if (state == DataState::kConnecting) {
      return;
    }
    for (auto &buffer : std::exchange(_held, {})) {
      if (state == DataState::kOpen) {
        SendNow(std::move(buffer));
      } else {
        DecreaseBufferedAmount(buffer.size());
      }
    }
  }

  void RTCDataChannel::Close() {
    // read before locking: it's a call to the signaling thread, which takes the lock in OnStateChange
    auto current = _channel->state();
    {
      const std::scoped_lock lock(_closeMutex);
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
