//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/sctp_transport_interface.h>

#include "rtc_dtls_transport.h"

namespace python_webrtc {

  class RTCSctpTransport : public webrtc::SctpTransportObserverInterface {
  public:
    explicit RTCSctpTransport(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::SctpTransportInterface>);

    static RTCSctpTransport *Create(PeerConnectionFactory *, rtc::scoped_refptr<webrtc::SctpTransportInterface>);

    ~RTCSctpTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<
        RTCSctpTransport *, rtc::scoped_refptr<webrtc::SctpTransportInterface>, PeerConnectionFactory *
    > *holder();

    void OnStateChange(webrtc::SctpTransportInformation) override;

    RTCDtlsTransport *GetTransport();

    webrtc::SctpTransportState GetState();

    std::optional<double> GetMaxMessageSize();

    std::optional<int> GetMaxChannels();

  protected:
    void Stop();

  private:
    PeerConnectionFactory *_factory;
    rtc::scoped_refptr<webrtc::DtlsTransportInterface> _dtls_transport;
    rtc::scoped_refptr<webrtc::SctpTransportInterface> _transport;
  };

} // namespace python_webrtc
