//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "port_allocator.h"

#include <utility>
#include <vector>

#include <p2p/client/basic_port_allocator.h>

namespace python_webrtc {

  namespace {

    // The networks of a manager shared by connections, which notifies a change only when they are different
    class NetworkManagerView : public webrtc::NetworkManager {
    public:
      explicit NetworkManagerView(webrtc::NetworkManager &shared) : _shared(shared) {}

      ~NetworkManagerView() override {
        _shared.UnsubscribeNetworksChanged(this);
        _shared.UnsubscribeError(this);
      }

      NetworkManagerView(const NetworkManagerView &) = delete;
      NetworkManagerView &operator=(const NetworkManagerView &) = delete;

      void StartUpdating() override {
        // a new session, like after an ICE restart, allocates its ports on the next notification
        _notified = false;
        if (_starts++ == 0) {
          _shared.SubscribeNetworksChanged(this, [this]() { OnNetworksChanged(); });
          _shared.SubscribeError(this, [this]() { NotifyError(); });
        }
        _shared.StartUpdating();
      }

      void StopUpdating() override {
        _shared.StopUpdating();
        if (--_starts == 0) {
          _shared.UnsubscribeNetworksChanged(this);
          _shared.UnsubscribeError(this);
        }
      }

      [[nodiscard]] std::vector<const webrtc::Network *> GetNetworks() const override { return _shared.GetNetworks(); }

      std::vector<const webrtc::Network *> GetAnyAddressNetworks() override { return _shared.GetAnyAddressNetworks(); }

      [[nodiscard]] EnumerationPermission enumeration_permission() const override {
        return _shared.enumeration_permission();
      }

      bool GetDefaultLocalAddress(int family, webrtc::IPAddress *address) const override {
        return _shared.GetDefaultLocalAddress(family, address);
      }

      [[nodiscard]] webrtc::MdnsResponderInterface *GetMdnsResponder() const override {
        return _shared.GetMdnsResponder();
      }

    private:
      using Snapshot = std::vector<std::pair<const webrtc::Network *, std::vector<webrtc::InterfaceAddress>>>;

      void OnNetworksChanged() {
        Snapshot networks;
        for (const auto *network : _shared.GetNetworks()) {
          networks.emplace_back(network, network->GetIPs());
        }
        if (_notified && networks == _seen) {
          return;
        }
        _notified = true;
        _seen = std::move(networks);
        NotifyNetworksChanged();
      }

      webrtc::NetworkManager &_shared;
      int _starts = 0;
      bool _notified = false;
      Snapshot _seen;
    };

    // What the allocator uses, made before and destroyed after it
    struct Owned {
      Owned(std::shared_ptr<webrtc::NetworkManager> networks, std::shared_ptr<webrtc::PacketSocketFactory> sockets)
          : networks(std::move(networks)), sockets(std::move(sockets)), view(*this->networks) {}

      std::shared_ptr<webrtc::NetworkManager> networks;
      std::shared_ptr<webrtc::PacketSocketFactory> sockets;
      NetworkManagerView view;
    };

    class ConnectionPortAllocator : private Owned, public webrtc::BasicPortAllocator {
    public:
      ConnectionPortAllocator(const webrtc::Environment &env, std::shared_ptr<webrtc::NetworkManager> networks,
                              std::shared_ptr<webrtc::PacketSocketFactory> sockets, bool tcpListen)
          : Owned(std::move(networks), std::move(sockets)), BasicPortAllocator(env, &view, this->sockets.get()) {
        // off by default: when both ends listen, every TCP port connects to every remote one (interfaces²)
        set_allow_tcp_listen(tcpListen);
      }

      webrtc::PortAllocatorSession *CreateSessionInternal(absl::string_view contentName, int component,
                                                          absl::string_view iceUfrag,
                                                          absl::string_view icePwd) override {
        // skips libwebrtc's 50 ms waits between gathering phases with nothing to allocate
        // the connection sets them right before it starts its candidate pool
        set_step_delay(0);
        return BasicPortAllocator::CreateSessionInternal(contentName, component, iceUfrag, icePwd);
      }
    };

  } // namespace

  std::unique_ptr<webrtc::PortAllocator> CreatePortAllocator(const webrtc::Environment &env,
                                                             std::shared_ptr<webrtc::NetworkManager> networks,
                                                             std::shared_ptr<webrtc::PacketSocketFactory> sockets,
                                                             bool tcpListen) {
    return std::make_unique<ConnectionPortAllocator>(env, std::move(networks), std::move(sockets), tcpListen);
  }

} // namespace python_webrtc
