//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_sctp_transport.h"

namespace python_webrtc {

  RTCSctpTransport::RTCSctpTransport(
      python_webrtc::PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::SctpTransportInterface> transport
  ) {
    _factory = factory;
    _transport = std::move(transport);

    _factory->_workerThread->Invoke<void>(RTC_FROM_HERE, [this]() {
      _dtls_transport = _transport->dtls_transport();
      _transport->RegisterObserver(this);
    });

    if (_transport->Information().state() == webrtc::SctpTransportState::kClosed) {
      Stop();
    }
  }

  RTCSctpTransport::~RTCSctpTransport() {
    _factory = nullptr;
    holder()->Release(this);
  }

  void RTCSctpTransport::Init(pybind11::module &m) {
    pybind11::class_<RTCSctpTransport>(m, "RTCSctpTransport")
        .def_property_readonly("transport", &RTCSctpTransport::GetTransport, pybind11::return_value_policy::reference)
        .def_property_readonly("state", &RTCSctpTransport::GetState)
        .def_property_readonly("maxMessageSize", &RTCSctpTransport::GetMaxMessageSize)
        .def_property_readonly("maxChannels", &RTCSctpTransport::GetMaxChannels);
  }

  InstanceHolder<RTCSctpTransport *, rtc::scoped_refptr<webrtc::SctpTransportInterface>, PeerConnectionFactory *> *
  RTCSctpTransport::holder() {
    static auto holder = new InstanceHolder<
        RTCSctpTransport *, rtc::scoped_refptr<webrtc::SctpTransportInterface>, PeerConnectionFactory *
    >(RTCSctpTransport::Create);
    return holder;
  }

  RTCSctpTransport *RTCSctpTransport::Create(
      PeerConnectionFactory *factory, rtc::scoped_refptr<webrtc::SctpTransportInterface> transport
  ) {
    // who caring about freeing memory?
    return new RTCSctpTransport(factory, std::move(transport));
  }

  void RTCSctpTransport::Stop() {
    _transport->UnregisterObserver();
  }

  void RTCSctpTransport::OnStateChange(webrtc::SctpTransportInformation info) {
    // TODO call callback

    if (info.state() == webrtc::SctpTransportState::kClosed) {
      Stop();
    }
  }

  RTCDtlsTransport *RTCSctpTransport::GetTransport() {
    return RTCDtlsTransport::holder()->GetOrCreate(_factory, _dtls_transport.get());
  }

  webrtc::SctpTransportState RTCSctpTransport::GetState() {
    return _transport->Information().state();
  }

  std::optional<double> RTCSctpTransport::GetMaxMessageSize() {
    auto size = _transport->Information().MaxMessageSize();
    if (size.has_value()) {
      return size.value();
    }

    return {};
  }

  std::optional<int> RTCSctpTransport::GetMaxChannels() {
    auto maxChannels = _transport->Information().MaxChannels();
    if (maxChannels.has_value()) {
      return maxChannels.value();
    }

    return {};
  }

} // namespace python_webrtc
