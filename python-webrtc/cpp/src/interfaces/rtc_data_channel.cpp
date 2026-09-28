//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_data_channel.h"

#include <pybind11/stl.h>

#include "../utils/gil.h"

namespace python_webrtc {

  RTCDataChannel::RTCDataChannel(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::DataChannelInterface> channel)
      : _factory(std::move(factory)), _channel(std::move(channel)) {
    Hold();
    // open only once the open event is delivered
    _surfacedState = webrtc::DataChannelInterface::DataState::kConnecting;
    // Posted, not blocking: wrappers are created under locks that the signaling thread may wait for.
    // The destructor unregisters with a call to the signaling thread, which runs after this.
    _factory->_signalingThread->PostTask(_alive.Guard([this]() {
      _lastState = _channel->state();
      if (_lastState != webrtc::DataChannelInterface::DataState::kOpen &&
          _lastState != webrtc::DataChannelInterface::DataState::kConnecting) {
        std::lock_guard<std::mutex> lock(_stateMutex);
        _surfacedState = _lastState;
      }
      // messages received meanwhile are delivered to the observer once it's registered, and are held too
      _channel->RegisterObserver(this);
      // a channel announced by the remote peer is open already, but its open event follows the datachannel one
      if (_lastState == webrtc::DataChannelInterface::DataState::kOpen) {
        Emit("open", static_cast<int>(_lastState));
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
    DropListeners();
    _channel = nullptr;
  }

  void RTCDataChannel::Init(pybind11::module &m) {
    pybind11::enum_<webrtc::DataChannelInterface::DataState>(m, "RTCDataChannelState")
        .value("connecting", webrtc::DataChannelInterface::DataState::kConnecting)
        .value("open", webrtc::DataChannelInterface::DataState::kOpen)
        .value("closing", webrtc::DataChannelInterface::DataState::kClosing)
        .value("closed", webrtc::DataChannelInterface::DataState::kClosed);

    pybind11::class_<DataChannelMessage>(m, "DataChannelMessage")
        .def_property_readonly("data", [](const DataChannelMessage &message) -> pybind11::object {
          if (message.binary) {
            return pybind11::bytes(message.data);
          }
          // the upper layers verify UTF-8, as libwebrtc doesn't
          return pybind11::reinterpret_steal<pybind11::object>(
              PyUnicode_DecodeUTF8(message.data.data(), static_cast<Py_ssize_t>(message.data.size()), "replace"));
        });

    pybind11::class_<RTCDataChannel, std::shared_ptr<RTCDataChannel>> cls(
        m, "RTCDataChannel", Listeners::TypeSetup<RTCDataChannel>());
    Listeners::Bind(cls);
    cls
        .def_property_readonly("label", nogil_fn([](RTCDataChannel &self) { return self._channel->label(); }))
        .def_property_readonly("ordered", nogil_fn([](RTCDataChannel &self) { return self._channel->ordered(); }))
        .def_property_readonly("maxPacketLifeTime", nogil_fn([](RTCDataChannel &self) {
          return self._channel->maxPacketLifeTime();
        }))
        .def_property_readonly("maxRetransmits", nogil_fn([](RTCDataChannel &self) {
          return self._channel->maxRetransmitsOpt();
        }))
        .def_property_readonly("protocol", nogil_fn([](RTCDataChannel &self) { return self._channel->protocol(); }))
        .def_property_readonly("negotiated", nogil_fn([](RTCDataChannel &self) {
          return self._channel->negotiated();
        }))
        .def_property_readonly("id", nogil_fn(&RTCDataChannel::GetId))
        .def_property_readonly("priority", nogil_fn([](RTCDataChannel &self) {
          return static_cast<int>(self._channel->priority().value());
        }))
        .def_property_readonly("readyState", nogil_fn(&RTCDataChannel::GetReadyState))
        .def("_surface", &RTCDataChannel::SurfaceState, nogil())
        .def("_decreaseBufferedAmount", &RTCDataChannel::DecreaseBufferedAmount, nogil())
        .def_property_readonly("bufferedAmount", nogil_fn(&RTCDataChannel::GetBufferedAmount))
        .def_property("bufferedAmountLowThreshold", nogil_fn(&RTCDataChannel::GetBufferedAmountLowThreshold),
                      nogil_fn(&RTCDataChannel::SetBufferedAmountLowThreshold))
        .def("send", &RTCDataChannel::Send, nogil())
        .def("close", &RTCDataChannel::Close, nogil())
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
      std::lock_guard<std::mutex> lock(_stateMutex);
      if (_closeRequested && state == webrtc::DataChannelInterface::DataState::kClosing) {
        // closing locally has shown the closing state already, and fires no event
        return;
      }
      if (!HasListeners() && !IsHeld()) {
        _surfacedState.reset();
      } else if (!_surfacedState) {
        _surfacedState = previous;
      }
    }

    auto value = static_cast<int>(state);
    switch (state) {
      case webrtc::DataChannelInterface::DataState::kOpen:
        Emit("open", value);
        break;
      case webrtc::DataChannelInterface::DataState::kClosing:
        Emit("closing", value);
        break;
      case webrtc::DataChannelInterface::DataState::kClosed: {
        auto error = _channel->error();
        // closing locally isn't an error, even if queued messages couldn't be sent
        bool closedLocally;
        {
          std::lock_guard<std::mutex> lock(_stateMutex);
          closedLocally = _closeRequested;
        }
        if (!error.ok() && !closedLocally) {
          Emit("error", RTCCallbackException(std::move(error)));
        }
        Emit("close", value);
        break;
      }
      default:
        break;
    }
  }

  webrtc::DataChannelInterface::DataState RTCDataChannel::GetReadyState() {
    auto state = _channel->state();
    std::lock_guard<std::mutex> lock(_stateMutex);
    return _surfacedState ? *_surfacedState : state;
  }

  void RTCDataChannel::SurfaceState(int state) {
    std::lock_guard<std::mutex> lock(_stateMutex);
    auto surfaced = static_cast<webrtc::DataChannelInterface::DataState>(state);
    // an open event that was queued before closing locally doesn't reopen the channel
    if (_closeRequested && surfaced == webrtc::DataChannelInterface::DataState::kOpen) {
      return;
    }
    _surfacedState = surfaced;
  }

  void RTCDataChannel::OnMessage(const webrtc::DataBuffer &buffer) {
    Emit("message", DataChannelMessage{std::string(buffer.data.cdata<char>(), buffer.size()), buffer.binary});
  }

  void RTCDataChannel::OnBufferedAmountChange(uint64_t sent_data_size) {
    // an internal event: Python decreases bufferedAmount when it's delivered
    Emit("_sent", sent_data_size);
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

  void RTCDataChannel::OnAnnounced() {
    std::lock_guard<std::mutex> lock(_stateMutex);
    // a channel announced by the remote peer is open when its datachannel event fires
    if (_lastState == webrtc::DataChannelInterface::DataState::kConnecting ||
        _lastState == webrtc::DataChannelInterface::DataState::kOpen) {
      _surfacedState = webrtc::DataChannelInterface::DataState::kOpen;
    }
  }

  void RTCDataChannel::OnPeerConnectionClosed() {
    Mute();
    {
      std::lock_guard<std::mutex> lock(_stateMutex);
      _surfacedState.reset();
    }
  }

  void RTCDataChannel::Send(const std::string &data, bool binary) {
    if (GetReadyState() != webrtc::DataChannelInterface::DataState::kOpen) {
      throw RTCException(webrtc::RTCErrorType::INVALID_STATE, "RTCDataChannel.readyState is not 'open'");
    }

    std::function<std::optional<double>()> getter;
    {
      std::lock_guard<std::mutex> lock(_getterMutex);
      getter = _maxMessageSizeGetter;
    }
    auto maxMessageSize = getter ? getter() : std::nullopt;
    if (maxMessageSize && static_cast<double>(data.size()) > *maxMessageSize) {
      throw pybind11::value_error("The message is larger than the maxMessageSize of the SCTP transport");
    }

    // a full queue fails the send, rather than libwebrtc closing the channel with an error
    if (_bufferedAmount + data.size() > webrtc::DataChannelInterface::MaxSendQueueSize()) {
      throw RTCException(webrtc::RTCErrorType::RESOURCE_EXHAUSTED, "The send queue of the RTCDataChannel is full");
    }
    _bufferedAmount += data.size();
    auto sent = _channel->Send(webrtc::DataBuffer(webrtc::CopyOnWriteBuffer(data.data(), data.size()), binary));
    if (!sent && _channel->state() == webrtc::DataChannelInterface::DataState::kOpen) {
      _bufferedAmount -= data.size();
      throw RTCException(webrtc::RTCErrorType::RESOURCE_EXHAUSTED, "The send queue of the RTCDataChannel is full");
    }

  }

  void RTCDataChannel::SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter) {
    std::lock_guard<std::mutex> lock(_getterMutex);
    _maxMessageSizeGetter = std::move(getter);
  }

  void RTCDataChannel::Close() {
    // read before locking: it's a call to the signaling thread, which takes the lock in OnStateChange
    auto current = _channel->state();
    {
      std::lock_guard<std::mutex> lock(_stateMutex);
      auto state = _surfacedState ? *_surfacedState : current;
      if (state == webrtc::DataChannelInterface::DataState::kClosing ||
          state == webrtc::DataChannelInterface::DataState::kClosed) {
        return;
      }
      _closeRequested = true;
      _surfacedState = webrtc::DataChannelInterface::DataState::kClosing;
    }
    _channel->Close();
  }

  uint64_t RTCDataChannel::GetBufferedAmount() {
    return _bufferedAmount;
  }

  uint64_t RTCDataChannel::GetBufferedAmountLowThreshold() {
    return _bufferedAmountLowThreshold;
  }

  void RTCDataChannel::SetBufferedAmountLowThreshold(uint64_t threshold) {
    _bufferedAmountLowThreshold = threshold;
  }

  std::optional<int> RTCDataChannel::GetId() {
    auto id = _channel->id();
    if (id < 0) {
      return std::nullopt;
    }
    return id;
  }

} // namespace python_webrtc
