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
    _iceTransport = RTCIceTransport::registry().GetOrCreate(_factory, _transport->ice_transport());

    BlockingCallOn(_factory->workerThread(), [this]() {
      _transport->RegisterObserver(this);
      registry().SetObserver(_transport.get(), this);
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
    // callbacks run on the network thread, so after this none of them can be running or start again
    BlockingCallOn(_factory->workerThread(), [this]() { Unobserve(); });

    _iceTransport = nullptr;
    _transport = nullptr;
  }

  void RTCDtlsTransport::Init(pybind11::module &m) {
    DefineBinding(pybind11::class_<RTCDtlsTransport, Binding, std::shared_ptr<RTCDtlsTransport>>(m, "RTCDtlsTransport"))
        .def_property_readonly("_id", &RTCDtlsTransport::Id)
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

  Registry<RTCDtlsTransport, webrtc::DtlsTransportInterface> &RTCDtlsTransport::registry() {
    static ForkLocal<Registry<RTCDtlsTransport, webrtc::DtlsTransportInterface>> registry;
    return registry.Get();
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
      auto emitter = _stateEmitter.Get();
      if (!emitter || !emitter(previous, information.state())) {
        _surfacedState.Changed(IsBound(), previous);
        Emit("statechange", information.state());
      }
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
    if (_observing && registry().TakeObserver(_transport.get(), this)) {
      _transport->UnregisterObserver();
    }
    _observing = false;
  }

  void RTCDtlsTransport::Stop() {
    Unobserve();
    _iceTransport->OnRTCDtlsTransportStopped();
  }

  void RTCDtlsTransport::OnPeerConnectionClosed() {
    Unbind();
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
    return _surfacedState.Shown(IsBound(), state);
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

  void RTCDtlsTransport::SetStateEmitter(std::function<StateEmitter> emitter) {
    _stateEmitter.Set(std::move(emitter));
  }

  webrtc::DtlsTransportState RTCDtlsTransport::GetCurrentState() {
    const std::scoped_lock lock(_mutex);
    return _state;
  }

  void RTCDtlsTransport::StateChanged(bool bound, webrtc::DtlsTransportState previous) {
    _surfacedState.Changed(bound, previous);
  }

  void RTCDtlsTransport::EmitStateChange(webrtc::DtlsTransportState state) {
    Emit("statechange", state);
  }

} // namespace python_webrtc
