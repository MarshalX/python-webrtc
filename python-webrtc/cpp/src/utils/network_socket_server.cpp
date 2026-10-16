//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "network_socket_server.h"

#include <memory>
#include <optional>
#include <utility>

#ifdef __APPLE__
#include <array>
#include <cerrno>

#include <rtc_base/time_utils.h>

#include <sys/event.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace python_webrtc {

  namespace {

    // Forwards to a socket, repeating its read event while the reads its handler makes succeed
    class DrainingSocket : public webrtc::Socket {
    public:
      DrainingSocket(webrtc::Socket *socket, webrtc::Buffer &scratch, int receiveBuffer)
          : _socket(socket), _scratch(scratch), _receiveBuffer(receiveBuffer) {
        // the analyzer loses the callbacks in libwebrtc's receiver list and reports them leaked
#ifndef __clang_analyzer__
        _socket->SubscribeReadEvent(this, [this](webrtc::Socket *) { Drain(); });
        _socket->SubscribeWriteEvent(this, [this](webrtc::Socket *) { NotifyWriteEvent(this); });
        _socket->SubscribeConnectEvent(this, [this](webrtc::Socket *) { NotifyConnectEvent(this); });
        _socket->SubscribeCloseEvent(this, [this](webrtc::Socket *, int error) { NotifyCloseEvent(this, error); });
#endif
      }

      ~DrainingSocket() override { *_alive = false; }
      DrainingSocket(const DrainingSocket &) = delete;
      DrainingSocket &operator=(const DrainingSocket &) = delete;
      DrainingSocket(DrainingSocket &&) = delete;
      DrainingSocket &operator=(DrainingSocket &&) = delete;

      // libwebrtc's UDP socket reads it for every packet it sends: kept from the bind, not asked of the kernel
      [[nodiscard]] webrtc::SocketAddress GetLocalAddress() const override {
        return _local ? *_local : _socket->GetLocalAddress();
      }
      [[nodiscard]] webrtc::SocketAddress GetRemoteAddress() const override { return _socket->GetRemoteAddress(); }
      int Bind(const webrtc::SocketAddress &address) override {
        _local.reset();
        const int result = _socket->Bind(address);
        if (result == 0) {
          if (auto local = _socket->GetLocalAddress(); !local.IsNil()) {
            _local = std::move(local);
          }
        }
        return result;
      }
      int Connect(const webrtc::SocketAddress &address) override {
        _local.reset();
        return _socket->Connect(address);
      }
      int Send(const void *data, size_t size) override { return _socket->Send(data, size); }
      int SendTo(const void *data, size_t size, const webrtc::SocketAddress &address) override {
        return _socket->SendTo(data, size, address);
      }
      int Recv(void *data, size_t size, int64_t *timestamp) override {
        return Read(_socket->Recv(data, size, timestamp));
      }
      int RecvFrom(void *data, size_t size, webrtc::SocketAddress *address, int64_t *timestamp) override {
        return Read(_socket->RecvFrom(data, size, address, timestamp));
      }
      int RecvFrom(ReceiveBuffer &buffer) override {
        ReceiveBuffer scratch(_scratch);
        int received = Read(_socket->RecvFrom(scratch));
        // drained: libwebrtc's UDP socket reads its local address to log a failed read, but not an empty one
        if (received < 0 && webrtc::IsBlockingError(_socket->GetError())) {
          received = 0;
        }
        buffer.payload.SetData(_scratch.data(), received > 0 ? static_cast<size_t>(received) : 0);
        buffer.source_address = scratch.source_address;
        buffer.arrival_time = scratch.arrival_time;
        buffer.ecn = scratch.ecn;
        return received;
      }
      int Listen(int backlog) override { return _socket->Listen(backlog); }
      webrtc::Socket *Accept(webrtc::SocketAddress *address) override { return _socket->Accept(address); }
      int Close() override {
        _local.reset();
        return _socket->Close();
      }
      [[nodiscard]] int GetError() const override { return _socket->GetError(); }
      void SetError(int error) override { _socket->SetError(error); }
      [[nodiscard]] ConnState GetState() const override { return _socket->GetState(); }
      int GetOption(Option option, int *value) override { return _socket->GetOption(option, value); }
      int SetOption(Option option, int value) override {
        if (option == OPT_RCVBUF && value < _receiveBuffer && _socket->SetOption(option, _receiveBuffer) == 0) {
          return 0;
        }
        return _socket->SetOption(option, value);
      }

    private:
      // bounded, so that one busy socket doesn't hold up the thread's other sockets and tasks
      static constexpr int kMaxReadsPerEvent = 64;

      int Read(int result) {
        _read = result >= 0;
        return result;
      }

      void Drain() {
        // a handler may destroy the socket
        const auto alive = _alive;
        for (int i = 0; i < kMaxReadsPerEvent; ++i) {
          _read = false;
          NotifyReadEvent(this);
          if (!*alive || !_read) {
            return;
          }
        }
      }

      std::unique_ptr<webrtc::Socket> _socket;
      // the server's, shared by its sockets
      webrtc::Buffer &_scratch;
      const int _receiveBuffer;
      std::shared_ptr<bool> _alive = std::make_shared<bool>(true);
      bool _read = false;
      std::optional<webrtc::SocketAddress> _local;
    };

#ifdef __APPLE__
    // A socket of the server whose events kqueue watches: libwebrtc changes them through these virtual methods
    class KqueueDispatcher : public webrtc::SocketDispatcher {
    public:
      explicit KqueueDispatcher(NetworkSocketServer &server) : SocketDispatcher(&server), _server(server) {}
      KqueueDispatcher(SOCKET descriptor, NetworkSocketServer &server)
          : SocketDispatcher(descriptor, &server), _server(server) {}
      ~KqueueDispatcher() override { _server.Unwatch(this); }
      KqueueDispatcher(const KqueueDispatcher &) = delete;
      KqueueDispatcher &operator=(const KqueueDispatcher &) = delete;
      KqueueDispatcher(KqueueDispatcher &&) = delete;
      KqueueDispatcher &operator=(KqueueDispatcher &&) = delete;

      int Close() override {
        _server.Unwatch(this);
        return SocketDispatcher::Close();
      }

    protected:
      void SetEnabledEvents(uint8_t events) override {
        SocketDispatcher::SetEnabledEvents(events);
        _server.Watch(this);
      }
      void EnableEvents(uint8_t events) override {
        SocketDispatcher::EnableEvents(events);
        _server.Watch(this);
      }
      void DisableEvents(uint8_t events) override {
        SocketDispatcher::DisableEvents(events);
        _server.Watch(this);
      }

    private:
      NetworkSocketServer &_server;
    };

    // As libwebrtc's ProcessEvents for poll(), with the socket error and the end of a stream from kqueue
    void ProcessEvent(webrtc::SocketDispatcher *dispatcher, const struct kevent &event) {
      const bool readable = event.filter == EVFILT_READ;
      const bool writable = event.filter == EVFILT_WRITE;
      const bool ended = (event.flags & EV_EOF) != 0;
      int error = 0;
      if ((event.flags & EV_ERROR) != 0) {
        error = static_cast<int>(event.data);
      } else if (ended) {
        error = static_cast<int>(event.fflags);
      }
      const uint32_t requested = dispatcher->GetRequestedEvents();
      uint32_t events = 0;
      if (readable) {
        if (error != 0 || (ended && dispatcher->IsDescriptorClosed())) {
          events |= webrtc::DE_CLOSE;
        } else if ((requested & webrtc::DE_ACCEPT) != 0) {
          events |= webrtc::DE_ACCEPT;
        } else {
          events |= webrtc::DE_READ;
        }
      }
      if (writable) {
        if ((requested & webrtc::DE_CONNECT) != 0) {
          if (error == 0) {
            events |= webrtc::DE_CONNECT;
          }
        } else {
          events |= webrtc::DE_WRITE;
        }
      }
      if (error != 0) {
        events |= webrtc::DE_CLOSE;
      }
      if (events != 0) {
        dispatcher->OnEvent(events, error);
      }
    }
#endif

  } // namespace

#ifdef __APPLE__
  NetworkSocketServer::NetworkSocketServer(int receiveBuffer) : _receiveBuffer(receiveBuffer), _kqueue(kqueue()) {
    RTC_CHECK(_kqueue >= 0) << "kqueue failed: " << errno;
    struct kevent wake{};
    EV_SET(&wake, 0, EVFILT_USER, EV_ADD | EV_CLEAR, 0, 0, nullptr);
    RTC_CHECK(kevent(_kqueue, &wake, 1, nullptr, 0, nullptr) == 0);
  }

  NetworkSocketServer::~NetworkSocketServer() {
    close(_kqueue);
  }

  webrtc::Socket *NetworkSocketServer::CreateSocket(int family, int type) {
    auto *dispatcher = new KqueueDispatcher(*this);
    if (!dispatcher->Create(family, type)) {
      delete dispatcher;
      return nullptr;
    }
    return Created(dispatcher, type);
  }

  webrtc::Socket *NetworkSocketServer::WrapSocket(SOCKET descriptor) {
    auto *dispatcher = new KqueueDispatcher(descriptor, *this);
    if (!dispatcher->Initialize()) {
      delete dispatcher;
      return nullptr;
    }
    // its events were set in libwebrtc's constructor, before this class's methods
    Watch(dispatcher);
    return dispatcher;
  }

  void NetworkSocketServer::Watch(webrtc::SocketDispatcher *dispatcher) {
    const int descriptor = dispatcher->GetDescriptor();
    if (descriptor == INVALID_SOCKET) {
      return;
    }
    const uint32_t requested = dispatcher->GetRequestedEvents();
    const bool read = (requested & (webrtc::DE_READ | webrtc::DE_ACCEPT)) != 0;
    const bool write = (requested & (webrtc::DE_WRITE | webrtc::DE_CONNECT)) != 0;
    const std::scoped_lock lock(_mutex);
    auto &watched = _watched[dispatcher];
    if (!watched) {
      watched = std::make_unique<Watched>(Watched{.dispatcher = dispatcher});
    }
    std::array<struct kevent, 2> changes{};
    int count = 0;
    if (read != watched->read) {
      EV_SET(&changes[count++], descriptor, EVFILT_READ, read ? EV_ADD : EV_DELETE, 0, 0, watched.get());
      watched->read = read;
    }
    if (write != watched->write) {
      EV_SET(&changes[count++], descriptor, EVFILT_WRITE, write ? EV_ADD : EV_DELETE, 0, 0, watched.get());
      watched->write = write;
    }
    if (count > 0) {
      (void)kevent(_kqueue, changes.data(), count, nullptr, 0, nullptr);
    }
  }

  void NetworkSocketServer::Unwatch(webrtc::SocketDispatcher *dispatcher) {
    const std::scoped_lock lock(_mutex);
    auto it = _watched.find(dispatcher);
    if (it == _watched.end()) {
      return;
    }
    const int descriptor = dispatcher->GetDescriptor();
    std::array<struct kevent, 2> changes{};
    int count = 0;
    if (descriptor != INVALID_SOCKET && it->second->read) {
      EV_SET(&changes[count++], descriptor, EVFILT_READ, EV_DELETE, 0, 0, nullptr);
    }
    if (descriptor != INVALID_SOCKET && it->second->write) {
      EV_SET(&changes[count++], descriptor, EVFILT_WRITE, EV_DELETE, 0, 0, nullptr);
    }
    if (count > 0) {
      (void)kevent(_kqueue, changes.data(), count, nullptr, 0, nullptr);
    }
    it->second->dispatcher = nullptr;
    _unwatched.push_back(std::move(it->second));
    _watched.erase(it);
  }

  bool NetworkSocketServer::Wait(webrtc::TimeDelta max_wait_duration, bool process_io) {
    if (!process_io) {
      // only waits for a wake up, which libwebrtc's poll() of its own signal also sees
      return PhysicalSocketServer::Wait(max_wait_duration, false);
    }
    {
      const std::scoped_lock lock(_mutex);
      _unwatched.clear();
    }
    timespec timeout{};
    const timespec *wait = nullptr;
    if (max_wait_duration.IsFinite()) {
      const int64_t micros = max_wait_duration.us();
      timeout.tv_sec = static_cast<time_t>(micros / webrtc::kNumMicrosecsPerSec);
      timeout.tv_nsec = static_cast<long>((micros % webrtc::kNumMicrosecsPerSec) * webrtc::kNumNanosecsPerMicrosec);
      wait = &timeout;
    }
    constexpr int kMaxEvents = 128;
    std::array<struct kevent, kMaxEvents> events{};
    const int count = kevent(_kqueue, nullptr, 0, events.data(), kMaxEvents, wait);
    if (count < 0) {
      return errno == EINTR;
    }
    for (int i = 0; i < count; ++i) {
      const auto &event = events[static_cast<size_t>(i)];
      if (event.filter == EVFILT_USER) {
        continue;
      }
      webrtc::SocketDispatcher *dispatcher = nullptr;
      {
        // a handler of an earlier event may have closed or destroyed it
        const std::scoped_lock lock(_mutex);
        dispatcher = static_cast<Watched *>(event.udata)->dispatcher;
      }
      if (dispatcher != nullptr) {
        ProcessEvent(dispatcher, event);
      }
    }
    return true;
  }

  void NetworkSocketServer::WakeUp() {
    struct kevent wake{};
    EV_SET(&wake, 0, EVFILT_USER, 0, NOTE_TRIGGER, 0, nullptr);
    (void)kevent(_kqueue, &wake, 1, nullptr, 0, nullptr);
    PhysicalSocketServer::WakeUp();
  }
#else
  NetworkSocketServer::NetworkSocketServer(int receiveBuffer) : _receiveBuffer(receiveBuffer) {}

  NetworkSocketServer::~NetworkSocketServer() = default;

  webrtc::Socket *NetworkSocketServer::CreateSocket(int family, int type) {
    return Created(webrtc::PhysicalSocketServer::CreateSocket(family, type), type);
  }
#endif

  webrtc::Socket *NetworkSocketServer::Created(webrtc::Socket *socket, int type) {
    if (socket == nullptr || type != SOCK_DGRAM) {
      return socket;
    }
    if (_receiveBuffer > 0) {
      (void)socket->SetOption(webrtc::Socket::OPT_RCVBUF, _receiveBuffer);
    }
    return new DrainingSocket(socket, _scratch, _receiveBuffer);
  }

} // namespace python_webrtc
