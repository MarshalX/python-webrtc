//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <mutex>

#include <api/ice_transport_interface.h>
#include <p2p/base/ice_transport_internal.h>

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../enums/python_webrtc/rtc_ice_component.h"

namespace python_webrtc {

  class RTCIceTransport {
  public:
    explicit RTCIceTransport(PeerConnectionFactory *, webrtc::scoped_refptr<webrtc::IceTransportInterface>);

    static RTCIceTransport *Create(PeerConnectionFactory *, webrtc::scoped_refptr<webrtc::IceTransportInterface>);

    ~RTCIceTransport();

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCIceTransport *, webrtc::scoped_refptr<webrtc::IceTransportInterface>, PeerConnectionFactory *
    > *holder();

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

    RTCIceComponent _component = RTCIceComponent::kRtp;
    PeerConnectionFactory *_factory;
    webrtc::IceGatheringState _gathering_state = webrtc::IceGatheringState::kIceGatheringNew;
    std::mutex _mutex{};
    webrtc::IceRole _role = webrtc::IceRole::ICEROLE_UNKNOWN;
    webrtc::IceTransportState _state = webrtc::IceTransportState::kNew;
    webrtc::scoped_refptr<webrtc::IceTransportInterface> _transport;
  };

} // namespace python_webrtc
