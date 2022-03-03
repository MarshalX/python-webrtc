//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtls_transport.h"

namespace python_webrtc {

  static std::vector<rtc::Buffer> copyCertificates(const webrtc::DtlsTransportInformation& information) {
    auto certificates = information.remote_ssl_certificates();
    if (certificates) {
      auto size = certificates->GetSize();

      auto derCertificates = std::vector<rtc::Buffer>();
      derCertificates.reserve(size);

      for (unsigned long i = 0; i < size; ++i) {
        auto buffer = rtc::Buffer(1);
        certificates->Get(i).ToDER(&buffer);
        derCertificates.emplace_back(std::move(buffer));
      }

      return derCertificates;
    }

    return {};
  }

  RTCDtlsTransport::RTCDtlsTransport(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::DtlsTransportInterface> transport
  ) {
    _factory = factory;
    _transport = std::move(transport);

    _factory->_workerThread->Invoke<void>(RTC_FROM_HERE, [this]() {
      _transport->RegisterObserver(this);

      auto information = _transport->Information();
      _state = information.state();
      _certificates = copyCertificates(information);

      if (_state == webrtc::DtlsTransportState::kClosed) {
        Stop();
      }
    });
  }

  RTCDtlsTransport::~RTCDtlsTransport() {
    _factory = nullptr;
    holder()->Release(this);
  }

  void RTCDtlsTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCDtlsTransport>(m, "RTCDtlsTransport")
        .def_property_readonly("iceTransport", &RTCDtlsTransport::GetIceTransport)
        .def_property_readonly("state", &RTCDtlsTransport::GetState);
  }

  InstanceHolder<RTCDtlsTransport *, rtc::scoped_refptr<webrtc::DtlsTransportInterface>, PeerConnectionFactory *> *
  RTCDtlsTransport::holder() {
    static auto holder = new InstanceHolder<
        RTCDtlsTransport *, rtc::scoped_refptr<webrtc::DtlsTransportInterface>, PeerConnectionFactory *
    >(RTCDtlsTransport::Create);
    return holder;
  }

  RTCDtlsTransport *RTCDtlsTransport::Create(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::DtlsTransportInterface> transport
  ) {
    // who caring about freeing memory?
    return new RTCDtlsTransport(factory, std::move(transport));
  }

  void RTCDtlsTransport::OnStateChange(webrtc::DtlsTransportInformation information) {
    {
      std::lock_guard<std::mutex> lock(_mutex);
      _state = information.state();
      _certificates = copyCertificates(information);
    }

    // TODO call callback

    if (information.state() == webrtc::DtlsTransportState::kClosed) {
      Stop();
    }
  }

  void RTCDtlsTransport::OnError(webrtc::RTCError rtcError) {
    // TODO call callback
  }

  void RTCDtlsTransport::Stop() {
    _transport->UnregisterObserver();
    auto ice_transport = RTCIceTransport::holder()->GetOrCreate(_factory, _transport->ice_transport());
    ice_transport->OnRTCDtlsTransportStopped();
  }

  RTCIceTransport *RTCDtlsTransport::GetIceTransport() {
    return RTCIceTransport::holder()->GetOrCreate(_factory, _transport->ice_transport());
  }

  webrtc::DtlsTransportState RTCDtlsTransport::GetState() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _state;
  }

} // namespace python_webrtc
