//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_PORT_ALLOCATOR_H_
#define PYTHON_WEBRTC_UTILS_PORT_ALLOCATOR_H_

#include <memory>

#include <api/environment/environment.h>
#include <api/packet_socket_factory.h>
#include <p2p/base/port_allocator.h>
#include <rtc_base/network.h>

namespace python_webrtc {

  // A connection's allocator: gathers again only on real network changes; network thread
  std::unique_ptr<webrtc::PortAllocator> CreatePortAllocator(const webrtc::Environment &env,
                                                             std::shared_ptr<webrtc::NetworkManager> networks,
                                                             std::shared_ptr<webrtc::PacketSocketFactory> sockets,
                                                             bool tcpListen);

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_PORT_ALLOCATOR_H_
