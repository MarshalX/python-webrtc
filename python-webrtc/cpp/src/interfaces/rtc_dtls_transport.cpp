//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtls_transport.h"
#include "../utils/gil.h"

namespace python_webrtc {

  static std::vector<webrtc::Buffer> copyCertificates(const webrtc::DtlsTransportInformation& information) {
    auto certificates = information.remote_ssl_certificates();
    if (certificates) {
      auto size = certificates->GetSize();

      auto derCertificates = std::vector<webrtc::Buffer>();
      derCertificates.reserve(size);

      for (unsigned long i = 0; i < size; ++i) {
        auto buffer = webrtc::Buffer(1);
        certificates->Get(i).ToDER(&buffer);
        derCertificates.emplace_back(std::move(buffer));
      }

      return derCertificates;
    }

    return {};
  }

  RTCDtlsTransport::RTCDtlsTransport(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::DtlsTransportInterface> transport
  ) : _factory(std::move(factory)), _transport(std::move(transport)) {
    _iceTransport = RTCIceTransport::holder().GetOrCreate(_factory, _transport->ice_transport());

    _factory->_workerThread->BlockingCall([this]() {
      _transport->RegisterObserver(this);
      _observing = true;

      auto information = _transport->Information();
      _state = information.state();
      _certificates = copyCertificates(information);

      if (_state == webrtc::DtlsTransportState::kClosed) {
        Stop();
      }
    });
  }

  RTCDtlsTransport::~RTCDtlsTransport() {
    gil_release_if_held release;

    // the transport has a single observer slot, a newer wrapper of it may have taken it over already
    auto replaced = holder().HasLive(_transport.get());
    // callbacks run on the network thread, so after this none of them can be running or start again
    _factory->_workerThread->BlockingCall([this, replaced]() {
      if (_observing && !replaced) {
        _transport->UnregisterObserver();
      }
      _observing = false;
    });

    _iceTransport = nullptr;
    _transport = nullptr;
  }

  void RTCDtlsTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCDtlsTransport, std::shared_ptr<RTCDtlsTransport>>(m, "RTCDtlsTransport")
        .def_property_readonly("iceTransport", nogil_fn(&RTCDtlsTransport::GetIceTransport))
        .def_property_readonly("state", nogil_fn(&RTCDtlsTransport::GetState));
  }

  InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface> &RTCDtlsTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface>();
    return *holder;
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
    if (_observing) {
      _transport->UnregisterObserver();
      _observing = false;
    }
    _iceTransport->OnRTCDtlsTransportStopped();
  }

  std::shared_ptr<RTCIceTransport> RTCDtlsTransport::GetIceTransport() {
    return _iceTransport;
  }

  webrtc::DtlsTransportState RTCDtlsTransport::GetState() {
    std::lock_guard<std::mutex> lock(_mutex);
    return _state;
  }

} // namespace python_webrtc
