//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtls_transport.h"

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/buffer.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  namespace {

    std::vector<webrtc::Buffer> copyCertificates(const webrtc::DtlsTransportInformation &information) {
      const auto *certificates = information.remote_ssl_certificates();
      if (certificates != nullptr) {
        auto size = certificates->GetSize();

        auto derCertificates = std::vector<webrtc::Buffer>();
        derCertificates.reserve(size);

        for (unsigned long i = 0; i < size; ++i) {
          webrtc::Buffer buffer;
          certificates->Get(i).ToDER(&buffer);
          derCertificates.emplace_back(std::move(buffer));
        }

        return derCertificates;
      }

      return {};
    }

  } // namespace

  RTCDtlsTransport::RTCDtlsTransport(std::shared_ptr<PeerConnectionFactory> factory,
                                     webrtc::scoped_refptr<webrtc::DtlsTransportInterface> transport)
      : _factory(std::move(factory)), _transport(std::move(transport)) {
    _iceTransport = RTCIceTransport::holder().GetOrCreate(_factory, _transport->ice_transport());

    _factory->workerThread()->BlockingCall([this]() {
      _transport->RegisterObserver(this);
      holder().SetObserver(_transport.get(), this);
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
    const BlockingDestructor release("RTCDtlsTransport");

    // callbacks run on the network thread, so after this none of them can be running or start again
    _factory->workerThread()->BlockingCall([this]() { Unobserve(); });

    _iceTransport = nullptr;
    _transport = nullptr;
    DropListeners();
  }

  void RTCDtlsTransport::Init(pybind11::module &m) {
    Listeners::BindClass<RTCDtlsTransport>(m, "RTCDtlsTransport")
        .def_property_readonly("iceTransport", nogil_fn(&RTCDtlsTransport::GetIceTransport))
        .def_property_readonly("state", nogil_fn(&RTCDtlsTransport::GetState))
        .def("getRemoteCertificates",
             [](RTCDtlsTransport &self) {
               pybind11::list certificates;
               for (const auto &certificate : self.GetRemoteCertificates()) {
                 certificates.append(Bytes(certificate.data(), certificate.size()));
               }
               return certificates;
             })
        .def("_surfaceState", &RTCDtlsTransport::SurfaceState, nogil(), pybind11::arg("state"));
  }

  InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface> &RTCDtlsTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto *holder = new InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface>();
    return *holder;
  }

  void RTCDtlsTransport::OnStateChange(webrtc::DtlsTransportInformation information) {
    bool changed = false;
    webrtc::DtlsTransportState previous{};
    {
      const std::scoped_lock lock(_mutex);
      previous = _state;
      changed = _state != information.state();
      _state = information.state();
      _certificates = copyCertificates(information);
    }

    if (changed) {
      if (information.state() == webrtc::DtlsTransportState::kFailed) {
        // libwebrtc tells no more than that the handshake failed
        webrtc::RTCError error(webrtc::RTCErrorType::OPERATION_ERROR_WITH_DATA, "The DTLS transport failed");
        error.set_error_detail(webrtc::RTCErrorDetailType::DTLS_FAILURE);
        Emit("error", RTCCallbackException(std::move(error)));
      }
      _surfacedState.Changed(IsTracked(), previous);
      Emit("statechange", information.state());
    }

    if (information.state() == webrtc::DtlsTransportState::kClosed) {
      Stop();
    }
  }

  void RTCDtlsTransport::OnError(webrtc::RTCError rtcError) {
    Emit("error", RTCCallbackException(std::move(rtcError)));
  }

  void RTCDtlsTransport::Unobserve() {
    // a newer wrapper of the transport may have taken its single observer slot
    if (_observing && holder().TakeObserver(_transport.get(), this)) {
      _transport->UnregisterObserver();
    }
    _observing = false;
  }

  void RTCDtlsTransport::Stop() {
    Unobserve();
    _iceTransport->OnRTCDtlsTransportStopped();
  }

  void RTCDtlsTransport::OnPeerConnectionClosed() {
    Mute();
    _surfacedState.Reset();
  }

  std::shared_ptr<RTCIceTransport> RTCDtlsTransport::GetIceTransport() {
    return _iceTransport;
  }

  webrtc::DtlsTransportState RTCDtlsTransport::GetState() {
    webrtc::DtlsTransportState state{};
    {
      const std::scoped_lock lock(_mutex);
      state = _state;
    }
    return _surfacedState.Get(state);
  }

  std::vector<webrtc::Buffer> RTCDtlsTransport::GetRemoteCertificates() {
    const std::scoped_lock lock(_mutex);
    std::vector<webrtc::Buffer> certificates;
    certificates.reserve(_certificates.size());
    for (const auto &certificate : _certificates) {
      certificates.emplace_back(certificate.data(), certificate.size());
    }
    return certificates;
  }

  void RTCDtlsTransport::SurfaceState(webrtc::DtlsTransportState state) {
    _surfacedState.Surface(state);
  }

} // namespace python_webrtc
