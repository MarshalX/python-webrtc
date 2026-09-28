//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/dtls_transport_interface.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "peer_connection_factory.h"
#include "rtc_ice_transport.h"
#include "../exceptions.h"
#include "../utils/listeners.h"

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

    std::shared_ptr<RTCIceTransport> GetIceTransport();

    webrtc::DtlsTransportState GetState();

    void SurfaceState(int state);

  protected:
    void Stop();

  public:
    // a closed connection fires no events of its transports, which show their current state
    void OnPeerConnectionClosed() {
      Mute();
      _surfacedState.Reset();
    }

  private:
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
