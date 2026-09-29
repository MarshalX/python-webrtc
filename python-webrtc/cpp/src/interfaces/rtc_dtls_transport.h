//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <memory>
#include <mutex>
#include <vector>

#include <api/dtls_transport_interface.h>

#include <pybind11/pybind11.h>

#include "peer_connection_factory.h"
#include "rtc_ice_transport.h"
#include "../utils/instance_holder.h"
#include "../utils/listeners.h"
#include "../utils/surfaced.h"
#include "../enums/enums.h"

namespace python_webrtc {

  class RTCDtlsTransport : public webrtc::DtlsTransportObserverInterface, public Listeners, public SingleObserverSlot {
  public:
    explicit RTCDtlsTransport(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::DtlsTransportInterface>);

    ~RTCDtlsTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface> &holder();

    webrtc::scoped_refptr<webrtc::DtlsTransportInterface> transport() { return _transport; }

    void OnStateChange(webrtc::DtlsTransportInformation) override;

    void OnError(webrtc::RTCError) override;

    // a closed connection fires no events of its transports, which show their current state
    void OnPeerConnectionClosed();

    std::shared_ptr<RTCIceTransport> GetIceTransport();

    webrtc::DtlsTransportState GetState();

    // the DER certificates of the remote peer
    std::vector<webrtc::Buffer> GetRemoteCertificates();

    // see Surfaced
    void SurfaceState(webrtc::DtlsTransportState state);

  private:
    // on the network thread
    void Stop();

    // unregisters, unless a newer wrapper took the observer slot (on the network thread)
    void Unobserve();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::DtlsTransportInterface> _transport;
    // a dtls transport runs over the same ice transport for its whole life
    std::shared_ptr<RTCIceTransport> _iceTransport;

    // accessed on the network thread only
    bool _observing = false;

    std::mutex _mutex;
    webrtc::DtlsTransportState _state;
    Surfaced<webrtc::DtlsTransportState> _surfacedState;
    std::vector<webrtc::Buffer> _certificates;
  };

} // namespace python_webrtc
