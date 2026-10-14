//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_NETWORK_SOCKET_SERVER_H_
#define PYTHON_WEBRTC_UTILS_NETWORK_SOCKET_SERVER_H_

#include <rtc_base/buffer.h>
#include <rtc_base/physical_socket_server.h>

#ifdef __APPLE__
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>
#endif

namespace python_webrtc {

  // The network thread's sockets: UDP drains every datagram into one shared buffer; Apple waits with kqueue, not poll
  class NetworkSocketServer : public webrtc::PhysicalSocketServer {
  public:
    NetworkSocketServer();
    ~NetworkSocketServer() override;
    NetworkSocketServer(const NetworkSocketServer &) = delete;
    NetworkSocketServer &operator=(const NetworkSocketServer &) = delete;
    NetworkSocketServer(NetworkSocketServer &&) = delete;
    NetworkSocketServer &operator=(NetworkSocketServer &&) = delete;

    webrtc::Socket *CreateSocket(int family, int type) override;

#ifdef __APPLE__
    webrtc::Socket *WrapSocket(SOCKET descriptor) override;
    bool Wait(webrtc::TimeDelta max_wait_duration, bool process_io) override;
    void WakeUp() override;

    // the events a socket asks for, as kqueue filters
    void Watch(webrtc::SocketDispatcher *dispatcher);
    void Unwatch(webrtc::SocketDispatcher *dispatcher);
#endif

  private:
    webrtc::Socket *Created(webrtc::Socket *socket, int type);

    webrtc::Buffer _scratch;

#ifdef __APPLE__
    struct Watched {
      webrtc::SocketDispatcher *dispatcher = nullptr;
      bool read = false;
      bool write = false;
    };

    const int _kqueue;
    std::mutex _mutex;
    std::unordered_map<webrtc::SocketDispatcher *, std::unique_ptr<Watched>> _watched;
    // unwatched during a wait, freed at the next: a kevent of the batch may still point to it
    std::vector<std::unique_ptr<Watched>> _unwatched;
#endif
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_NETWORK_SOCKET_SERVER_H_
