//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_dtls_transport.h"

#include <pybind11/stl.h>

#include "../exceptions.h"
#include "../utils/gil.h"
#include "../utils/libwebrtc_thread.h"

namespace python_webrtc {

  static std::vector<webrtc::Buffer> copyCertificates(const webrtc::DtlsTransportInformation& information) {
    auto certificates = information.remote_ssl_certificates();
    if (certificates) {
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
    BlockingDestructor release("RTCDtlsTransport");

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
    DropListeners();
  }

  void RTCDtlsTransport::Init(pybind11::module &m) {
    Listeners::BindClass<RTCDtlsTransport>(m, "RTCDtlsTransport")
        .def_property_readonly("iceTransport", nogil_fn(&RTCDtlsTransport::GetIceTransport))
        .def_property_readonly("state", nogil_fn(&RTCDtlsTransport::GetState))
        .def("getRemoteCertificates", [](RTCDtlsTransport &self) {
          pybind11::list certificates;
          for (const auto &certificate: self.GetRemoteCertificates()) {
            auto data = reinterpret_cast<const char *>(certificate.data());
            certificates.append(pybind11::bytes(data, certificate.size()));
          }
          return certificates;
        })
        .def("_surfaceState", &RTCDtlsTransport::SurfaceState, nogil(), pybind11::arg("state"));
  }

  InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface> &RTCDtlsTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCDtlsTransport, webrtc::DtlsTransportInterface>();
    return *holder;
  }

  void RTCDtlsTransport::OnStateChange(webrtc::DtlsTransportInformation information) {
    bool changed;
    webrtc::DtlsTransportState previous;
    {
      std::lock_guard<std::mutex> lock(_mutex);
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

  void RTCDtlsTransport::Stop() {
    if (_observing) {
      _transport->UnregisterObserver();
      _observing = false;
    }
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
    webrtc::DtlsTransportState state;
    {
      std::lock_guard<std::mutex> lock(_mutex);
      state = _state;
    }
    return _surfacedState.Get(state);
  }

  std::vector<webrtc::Buffer> RTCDtlsTransport::GetRemoteCertificates() {
    std::lock_guard<std::mutex> lock(_mutex);
    std::vector<webrtc::Buffer> certificates;
    for (const auto &certificate: _certificates) {
      certificates.emplace_back(certificate.data(), certificate.size());
    }
    return certificates;
  }

  void RTCDtlsTransport::SurfaceState(webrtc::DtlsTransportState state) {
    _surfacedState.Surface(state);
  }

} // namespace python_webrtc
