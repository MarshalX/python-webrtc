//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>

#include <api/ice_transport_interface.h>
#include <p2p/base/ice_transport_internal.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../enums/python_webrtc/rtc_ice_component.h"

namespace python_webrtc {

  class RTCIceTransport {
  public:
    explicit RTCIceTransport(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::IceTransportInterface>);

    ~RTCIceTransport();

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCIceTransport, webrtc::IceTransportInterface> &holder();

    void OnRTCDtlsTransportStopped();

    RTCIceComponent GetComponent();

    webrtc::IceGatheringState GetGatheringState();

    webrtc::IceRole GetRole();

    webrtc::IceTransportState GetState();

  protected:
    void Stop();

  private:
    void OnStateChanged(webrtc::IceTransportInternal *);

    void OnGatheringStateChanged(webrtc::IceTransportInternal *);

    void TakeSnapshot();

    std::shared_ptr<PeerConnectionFactory> _factory;

    // Accessed on the network thread only. State change callbacks can't be unsubscribed from,
    // so they check this flag and become no-ops once the wrapper is gone.
    std::shared_ptr<bool> _alive = std::make_shared<bool>(true);
    webrtc::IceTransportInternal *_subscribed = nullptr;

    RTCIceComponent _component = RTCIceComponent::kRtp;
    webrtc::IceGatheringState _gathering_state = webrtc::IceGatheringState::kIceGatheringNew;
    std::mutex _mutex{};
    webrtc::IceRole _role = webrtc::IceRole::ICEROLE_UNKNOWN;
    webrtc::IceTransportState _state = webrtc::IceTransportState::kNew;
    webrtc::scoped_refptr<webrtc::IceTransportInterface> _transport;
  };

} // namespace python_webrtc
