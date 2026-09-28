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

      if (_transport->Information().state() == webrtc::SctpTransportState::kClosed) {
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
  }

  void RTCSctpTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCSctpTransport, std::shared_ptr<RTCSctpTransport>>(m, "RTCSctpTransport")
        .def_property_readonly("transport", nogil_fn(&RTCSctpTransport::GetTransport))
        .def_property_readonly("state", nogil_fn(&RTCSctpTransport::GetState))
        .def_property_readonly("maxMessageSize", nogil_fn(&RTCSctpTransport::GetMaxMessageSize))
        .def_property_readonly("maxChannels", nogil_fn(&RTCSctpTransport::GetMaxChannels));
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
    // TODO call callback

    if (info.state() == webrtc::SctpTransportState::kClosed) {
      Stop();
    }
  }

  std::shared_ptr<RTCDtlsTransport> RTCSctpTransport::GetTransport() {
    return _dtlsTransport;
  }

  webrtc::SctpTransportInformation RTCSctpTransport::Information() {
    // the information is owned by the network thread
    return _factory->_workerThread->BlockingCall([this]() { return _transport->Information(); });
  }

  webrtc::SctpTransportState RTCSctpTransport::GetState() {
    return Information().state();
  }

  std::optional<double> RTCSctpTransport::GetMaxMessageSize() {
    auto size = Information().MaxMessageSize();
    if (size.has_value()) {
      return size.value();
    }

    return {};
  }

  std::optional<int> RTCSctpTransport::GetMaxChannels() {
    auto maxChannels = Information().MaxChannels();
    if (maxChannels.has_value()) {
      return maxChannels.value();
    }

    return {};
  }

} // namespace python_webrtc
