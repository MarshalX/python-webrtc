//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <api/sctp_transport_interface.h>

#include "rtc_dtls_transport.h"
#include "../utils/listeners.h"

namespace python_webrtc {

  class RTCSctpTransport : public webrtc::SctpTransportObserverInterface, public Listeners, public SingleObserverSlot {
  public:
    explicit RTCSctpTransport(std::shared_ptr<PeerConnectionFactory>, webrtc::scoped_refptr<webrtc::SctpTransportInterface>);

    ~RTCSctpTransport() override;

    static void Init(pybind11::module &m);

    static InstanceHolder<RTCSctpTransport, webrtc::SctpTransportInterface> &holder();

    webrtc::scoped_refptr<webrtc::SctpTransportInterface> transport() { return _transport; }

    void OnStateChange(webrtc::SctpTransportInformation) override;

    std::shared_ptr<RTCDtlsTransport> GetTransport();

    webrtc::SctpTransportState GetState();

    void SurfaceState(int state);

    std::optional<double> GetMaxMessageSize();

    // what the connection computes from its descriptions, until the transport knows it
    void SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter);

    std::optional<int> GetMaxChannels();

  protected:
    void Stop();

  public:
    // a closed connection fires no events of its transports, which show their current state
    void OnPeerConnectionClosed() {
      Mute();
      _surfacedState.Reset();
    }

  private:
    webrtc::SctpTransportInformation Information();

    std::shared_ptr<PeerConnectionFactory> _factory;
    webrtc::scoped_refptr<webrtc::SctpTransportInterface> _transport;
    // an sctp transport runs over the same dtls transport for its whole life
    std::shared_ptr<RTCDtlsTransport> _dtlsTransport;

    // accessed on the network thread only
    bool _observing = false;

    // on the network thread
    webrtc::SctpTransportState _lastState = webrtc::SctpTransportState::kNew;
    Surfaced<webrtc::SctpTransportState> _surfacedState;

    std::mutex _getterMutex;
    std::function<std::optional<double>()> _maxMessageSizeGetter;
  };

} // namespace python_webrtc
