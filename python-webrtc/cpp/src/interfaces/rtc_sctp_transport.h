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
    explicit RTCSctpTransport(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::SctpTransportInterface>);

    ~RTCSctpTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCSctpTransport, webrtc::SctpTransportInterface> &holder();

    webrtc::scoped_refptr<webrtc::SctpTransportInterface> transport() { return _transport; }

    void OnStateChange(webrtc::SctpTransportInformation) override;

    std::shared_ptr<RTCDtlsTransport> GetTransport();

    webrtc::SctpTransportState GetState();

    std::optional<double> GetMaxMessageSize();

    std::optional<int> GetMaxChannels();

  protected:
    void Stop();

  private:
    webrtc::SctpTransportInformation Information();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::SctpTransportInterface> _transport;
    // an sctp transport runs over the same dtls transport for its whole life
    std::shared_ptr<RTCDtlsTransport> _dtlsTransport;

    // accessed on the network thread only
    bool _observing = false;
  };

} // namespace python_webrtc
