//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_sctp_transport.h"
#include "../utils/gil.h"

namespace python_webrtc {

  RTCSctpTransport::RTCSctpTransport(
      std::shared_ptr<PeerConnectionFactory> factory, webrtc::scoped_refptr<webrtc::SctpTransportInterface> transport
  ) : _factory(std::move(factory)), _transport(std::move(transport)) {
    webrtc::scoped_refptr<webrtc::DtlsTransportInterface> dtlsTransport;
    _factory->_workerThread->BlockingCall([this, &dtlsTransport]() {
      dtlsTransport = _transport->dtls_transport();
      _transport->RegisterObserver(this);
      _observing = true;
      _lastState = _transport->Information().state();

      if (_lastState == webrtc::SctpTransportState::kClosed) {
        Stop();
      }
    });

    _dtlsTransport = RTCDtlsTransport::holder().GetOrCreate(_factory, dtlsTransport);
  }

  RTCSctpTransport::~RTCSctpTransport() {
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

    _dtlsTransport = nullptr;
    _transport = nullptr;
    DropListeners();
  }

  void RTCSctpTransport::Init(pybind11::module &m) {
    Listeners::BindClass<RTCSctpTransport>(m, "RTCSctpTransport")
        .def_property_readonly("transport", nogil_fn(&RTCSctpTransport::GetTransport))
        .def_property_readonly("state", nogil_fn(&RTCSctpTransport::GetState))
        .def_property_readonly("maxMessageSize", nogil_fn(&RTCSctpTransport::GetMaxMessageSize))
        .def_property_readonly("maxChannels", nogil_fn(&RTCSctpTransport::GetMaxChannels))
        .def("_surfaceState", &RTCSctpTransport::SurfaceState, nogil(), pybind11::arg("state"));
  }

  InstanceHolder<RTCSctpTransport, webrtc::SctpTransportInterface> &RTCSctpTransport::holder() {
    // never destroyed: wrappers may outlive static destructors
    static auto holder = new InstanceHolder<RTCSctpTransport, webrtc::SctpTransportInterface>();
    return *holder;
  }

  void RTCSctpTransport::Stop() {
    if (_observing) {
      _transport->UnregisterObserver();
      _observing = false;
    }
  }

  void RTCSctpTransport::OnStateChange(webrtc::SctpTransportInformation info) {
    if (info.state() != _lastState) {
      _surfacedState.Changed(IsTracked(), _lastState);
      _lastState = info.state();
      Emit("statechange", info.state());
    }

    if (info.state() == webrtc::SctpTransportState::kClosed) {
      Stop();
    }
  }

  void RTCSctpTransport::OnPeerConnectionClosed() {
    Mute();
    _surfacedState.Reset();
  }

  std::shared_ptr<RTCDtlsTransport> RTCSctpTransport::GetTransport() {
    return _dtlsTransport;
  }

  webrtc::SctpTransportInformation RTCSctpTransport::Information() {
    // the information is owned by the network thread
    return _factory->_workerThread->BlockingCall([this]() { return _transport->Information(); });
  }

  webrtc::SctpTransportState RTCSctpTransport::GetState() {
    return _surfacedState.Get(Information().state());
  }

  void RTCSctpTransport::SurfaceState(webrtc::SctpTransportState state) {
    _surfacedState.Surface(state);
  }

  std::optional<double> RTCSctpTransport::GetMaxMessageSize() {
    auto getter = _maxMessageSizeGetter.Get();
    return getter ? getter() : Information().MaxMessageSize();
  }

  void RTCSctpTransport::SetMaxMessageSizeGetter(std::function<std::optional<double>()> getter) {
    _maxMessageSizeGetter.Set(std::move(getter));
  }

  std::optional<int> RTCSctpTransport::GetMaxChannels() {
    // known once connected, as Python sees the state change along with its event
    auto state = GetState();
    if (state == webrtc::SctpTransportState::kNew || state == webrtc::SctpTransportState::kConnecting) {
      return {};
    }
    return Information().MaxChannels();
  }

} // namespace python_webrtc
