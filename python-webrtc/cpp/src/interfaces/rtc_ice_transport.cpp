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
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::IceTransportInterface> transport)
      : _factory(std::move(factory)), _transport(std::move(transport)) {
    _factory->_workerThread->BlockingCall([this]() {
      auto internal = _transport->internal();
      if (internal) {
        auto alive = _alive;
        internal->SubscribeIceTransportStateChanged(
            this, [this, alive](webrtc::IceTransportInternal *transport) {
              if (*alive) {
                OnStateChanged(transport);
              }
            });
        internal->AddGatheringStateCallback(
            this, [this, alive](webrtc::IceTransportInternal *transport) {
              if (*alive) {
                OnGatheringStateChanged(transport);
              }
            });
        _subscribed = internal;
      }
      TakeSnapshot();
      if (_state == webrtc::IceTransportState::kClosed) {
        Stop();
      }
    });
  }

  RTCIceTransport::~RTCIceTransport() {
    gil_release_if_held release;

    // callbacks run on the network thread, so after this none of them can be running or start again
    _factory->_workerThread->BlockingCall([this]() {
      *_alive = false;
      // the internal transport is gone (with its callbacks) once the ice transport is cleared
      if (_subscribed && _transport->internal() == _subscribed) {
        _subscribed->RemoveGatheringStateCallback(this);
      }
    });

    _transport = nullptr;
  }

  void RTCIceTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCIceTransport, std::shared_ptr<RTCIceTransport>>(m, "RTCIceTransport")
        .def_property_readonly("component", nogil_fn(&RTCIceTransport::GetComponent))
        .def_property_readonly("gatheringState", nogil_fn(&RTCIceTransport::GetGatheringState))
        .def_property_readonly("role", nogil_fn(&RTCIceTransport::GetRole))
        .def_property_readonly("state", nogil_fn(&RTCIceTransport::GetState));
  }

  InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface> &RTCIceTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface>();
    return *holder;
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
