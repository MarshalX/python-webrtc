//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <mutex>

#include <webrtc/api/ice_transport_interface.h>
#include <rtc_base/third_party/sigslot/sigslot.h>
#include "p2p/base/ice_transport_internal.h"

#include "peer_connection_factory.h"
#include "../utils/instance_holder.h"
#include "../enums/python_webrtc/rtc_ice_component.h"

namespace python_webrtc {

  class RTCIceTransport : public sigslot::has_slots<sigslot::multi_threaded_local> {
  public:
    explicit RTCIceTransport(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::IceTransportInterface>);

    static RTCIceTransport *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::IceTransportInterface>);

    ~RTCIceTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCIceTransport *, rtc::scoped_refptr<webrtc::IceTransportInterface>, PeerConnectionFactory *
    > *holder();

    void OnRTCDtlsTransportStopped();

    RTCIceComponent GetComponent();

    cricket::IceGatheringState GetGatheringState();

    cricket::IceRole GetRole();

    webrtc::IceTransportState GetState();

  protected:
    void Stop();

  private:
    void OnStateChanged(cricket::IceTransportInternal *);

    void OnGatheringStateChanged(cricket::IceTransportInternal *);

    void TakeSnapshot();

    RTCIceComponent _component = RTCIceComponent::kRtp;
    PeerConnectionFactory *_factory;
    cricket::IceGatheringState _gathering_state = cricket::IceGatheringState::kIceGatheringNew;
    std::mutex _mutex{};
    cricket::IceRole _role = cricket::IceRole::ICEROLE_UNKNOWN;
    webrtc::IceTransportState _state = webrtc::IceTransportState::kNew;
    rtc::scoped_refptr<webrtc::IceTransportInterface> _transport;
  };

} // namespace python_webrtc
