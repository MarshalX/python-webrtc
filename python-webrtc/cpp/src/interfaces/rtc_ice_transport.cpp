//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_ice_transport.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCIceTransport::RTCIceTransport(
      PeerConnectionFactory *factory, webrtc::scoped_refptr<webrtc::IceTransportInterface> transport) {
    _factory = factory;
    _transport = std::move(transport);

    _factory->_workerThread->BlockingCall([this]() {
      auto internal = _transport->internal();
      if (internal) {
        internal->SubscribeIceTransportStateChanged(
            this, [this](webrtc::IceTransportInternal *transport) { OnStateChanged(transport); });
        internal->AddGatheringStateCallback(
            this, [this](webrtc::IceTransportInternal *transport) { OnGatheringStateChanged(transport); });
      }
      TakeSnapshot();
      if (_state == webrtc::IceTransportState::kClosed) {
        Stop();
      }
    });
  }

  RTCIceTransport::~RTCIceTransport() {
    _factory = nullptr;
    holder()->Release(this);
  }

  void RTCIceTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCIceTransport>(m, "RTCIceTransport")
        .def_property_readonly("component", nogil_fn(&RTCIceTransport::GetComponent))
        .def_property_readonly("gatheringState", nogil_fn(&RTCIceTransport::GetGatheringState))
        .def_property_readonly("role", nogil_fn(&RTCIceTransport::GetRole))
        .def_property_readonly("state", nogil_fn(&RTCIceTransport::GetState));
  }

  InstanceHolder<RTCIceTransport *, webrtc::scoped_refptr<webrtc::IceTransportInterface>, PeerConnectionFactory *> *
  RTCIceTransport::holder() {
    static auto holder = new InstanceHolder<
        RTCIceTransport *, webrtc::scoped_refptr<webrtc::IceTransportInterface>, PeerConnectionFactory *
    >(RTCIceTransport::Create);
    return holder;
  }

  RTCIceTransport *RTCIceTransport::Create(
      PeerConnectionFactory *factory, webrtc::scoped_refptr<webrtc::IceTransportInterface> transport
  ) {
    // who caring about freeing memory?
    return new RTCIceTransport(factory, std::move(transport));
  }

  void RTCIceTransport::TakeSnapshot() {
    std::lock_guard<std::mutex> lock(_mutex);
    auto internal = _transport->internal();
    if (internal) {
      if (internal->component() == 1) {
        _component = RTCIceComponent::kRtp;
      } else {
        _component = RTCIceComponent::kRtcp;
      }

      _role = internal->GetIceRole();
      _state = internal->GetIceTransportState();
      _gathering_state = internal->gathering_state();
    } else {
      _state = webrtc::IceTransportState::kClosed;
      _gathering_state = webrtc::IceGatheringState::kIceGatheringComplete;
    }
  }

  void RTCIceTransport::OnRTCDtlsTransportStopped() {
    std::lock_guard<std::mutex> lock(_mutex);
    _state = webrtc::IceTransportState::kClosed;
    _gathering_state = webrtc::IceGatheringState::kIceGatheringComplete;
    Stop();
  }

  void RTCIceTransport::Stop() {

  }

  void RTCIceTransport::OnStateChanged(webrtc::IceTransportInternal *) {
    TakeSnapshot();

    // TODO call callback

    if (_state == webrtc::IceTransportState::kClosed) {
      Stop();
    }
  }

  void RTCIceTransport::OnGatheringStateChanged(webrtc::IceTransportInternal *) {
    TakeSnapshot();

    // TODO call callback
  }

  RTCIceComponent RTCIceTransport::GetComponent() {
    std::lock_guard<std::mutex> lock(_mutex);
    if (_component == 1) {
      return RTCIceComponent::kRtp;
    } else {
      return RTCIceComponent::kRtcp;
    }
  }

  webrtc::IceGatheringState RTCIceTransport::GetGatheringState() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _gathering_state;
  }

  webrtc::IceRole RTCIceTransport::GetRole() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _role;
  }

  webrtc::IceTransportState RTCIceTransport::GetState() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _state;
  }

} // namespace python_webrtc
