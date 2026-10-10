//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_DTLS_TRANSPORT_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_DTLS_TRANSPORT_H_

#include <functional>
#include <memory>
#include <mutex>
#include <vector>

#include <api/dtls_transport_interface.h>

#include <pybind11/pybind11.h>

#include "../enums/enums.h"
#include "../utils/locked_function.h"
#include "../utils/mailbox.h"
#include "../utils/native_object.h"
#include "../utils/registry.h"
#include "../utils/surfaced.h"
#include "peer_connection_factory.h"
#include "rtc_ice_transport.h"

namespace python_webrtc {

  class RTCDtlsTransport : public webrtc::DtlsTransportObserverInterface,
                           public NativeObject<RTCDtlsTransport>,
                           public Emitter<RTCDtlsTransport> {
  public:
    static constexpr const char *kName = "RTCDtlsTransport";

    explicit RTCDtlsTransport(std::shared_ptr<PeerConnectionFactory> factory,
                              webrtc::scoped_refptr<webrtc::DtlsTransportInterface> transport);

    ~RTCDtlsTransport() override;

    RTCDtlsTransport(const RTCDtlsTransport &) = delete;
    RTCDtlsTransport &operator=(const RTCDtlsTransport &) = delete;

    static void Init(pybind11::module &m);

    static Registry<RTCDtlsTransport, webrtc::DtlsTransportInterface> &registry();

    webrtc::scoped_refptr<webrtc::DtlsTransportInterface> transport() { return _transport; }

    void OnStateChange(webrtc::DtlsTransportInformation info) override;

    void OnError(webrtc::RTCError error) override;

    // a closed connection fires no events of its transports, which show their current state
    void OnPeerConnectionClosed();

    std::shared_ptr<RTCIceTransport> GetIceTransport();

    webrtc::DtlsTransportState GetState();

    // the DER certificates of the remote peer
    std::vector<webrtc::Buffer> GetRemoteCertificates();

    // see Surfaced
    void SurfaceState(webrtc::DtlsTransportState state);

    // see RTCIceTransport::StateEmitter
    using StateEmitter = bool(webrtc::DtlsTransportState previous, webrtc::DtlsTransportState state);

    void SetStateEmitter(std::function<StateEmitter> emitter);

    webrtc::DtlsTransportState GetCurrentState();

    void StateChanged(bool bound, webrtc::DtlsTransportState previous);

    void EmitStateChange(webrtc::DtlsTransportState state);

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
    LockedFunction<StateEmitter> _stateEmitter;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_DTLS_TRANSPORT_H_
