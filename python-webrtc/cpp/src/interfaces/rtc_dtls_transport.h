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

namespace python_webrtc {

  class RTCDtlsTransport : public webrtc::DtlsTransportObserverInterface {
  public:
    explicit RTCDtlsTransport(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::DtlsTransportInterface>);

    static RTCDtlsTransport *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::DtlsTransportInterface>);

    ~RTCDtlsTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCDtlsTransport *, rtc::scoped_refptr<webrtc::DtlsTransportInterface>, PeerConnectionFactory *
    > *holder();

    void OnStateChange(webrtc::DtlsTransportInformation) override;

    void OnError(webrtc::RTCError) override;

    RTCIceTransport *GetIceTransport();

    webrtc::DtlsTransportState GetState();

  protected:
    void Stop();

  private:
    std::mutex _mutex;
    webrtc::DtlsTransportState _state;
    std::vector<rtc::Buffer> _certificates;

    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::DtlsTransportInterface> _transport;
  };

} // namespace python_webrtc
