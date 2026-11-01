#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""A STUN server on the loopback interface (RFC 8489): it maps clients to a fixed address, to their own, or never."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
import struct
from typing import TYPE_CHECKING, cast

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

#: From TEST-NET-1 (RFC 5737), so it's no host's
MAPPED_ADDRESS = '192.0.2.10'

_MAGIC_COOKIE = 0x2112A442
_BINDING_REQUEST = 0x0001
_BINDING_SUCCESS = 0x0101
_XOR_MAPPED_ADDRESS = 0x0020
_IPV4 = 0x01
_HEADER = struct.Struct('!HHI12s')


class StunServer(asyncio.DatagramProtocol):
    """Maps each Binding request to :data:`MAPPED_ADDRESS`, or to its own address as a mirror.

    Bound to 127.0.0.1: replies from a wildcard socket can leave from another loopback address.
    """

    def __init__(self, *, silent: bool, mirror: bool) -> None:
        self.silent = silent
        self.mirror = mirror
        #: The Binding requests received
        self.requests = 0
        self._transport: asyncio.DatagramTransport | None = None

    @property
    def port(self) -> int:
        assert self._transport is not None
        address = cast('tuple[str, int]', self._transport.get_extra_info('sockname'))
        return address[1]

    @property
    def url(self) -> str:
        return f'stun:127.0.0.1:{self.port}'

    @override
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast('asyncio.DatagramTransport', transport)

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | object, int]) -> None:
        if len(data) < _HEADER.size:
            return
        message_type, _length, cookie, transaction = _HEADER.unpack_from(data)
        if message_type != _BINDING_REQUEST or cookie != _MAGIC_COOKIE:
            return

        self.requests += 1
        if self.silent or self._transport is None:
            return
        mapped = str(addr[0]) if self.mirror else MAPPED_ADDRESS
        self._transport.sendto(_binding_success(transaction, mapped, addr[1]), addr)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()


def _binding_success(transaction: bytes, address: str, port: int) -> bytes:
    """A Binding success response with the XOR-MAPPED-ADDRESS of an IPv4 address and port."""
    xor_port = port ^ (_MAGIC_COOKIE >> 16)
    xor_address = int(ipaddress.IPv4Address(address)) ^ _MAGIC_COOKIE
    value = struct.pack('!BBHI', 0, _IPV4, xor_port, xor_address)
    attribute = struct.pack('!HH', _XOR_MAPPED_ADDRESS, len(value)) + value
    return _HEADER.pack(_BINDING_SUCCESS, len(attribute), _MAGIC_COOKIE, transaction) + attribute


@contextlib.asynccontextmanager
async def stun_server(*, silent: bool = False, mirror: bool = False) -> AsyncGenerator[StunServer, None]:
    """A STUN server for the block; a silent one stands for a server that's unreachable."""
    loop = asyncio.get_running_loop()
    _, server = await loop.create_datagram_endpoint(
        lambda: StunServer(silent=silent, mirror=mirror), local_addr=('127.0.0.1', 0), family=socket.AF_INET
    )
    try:
        yield server
    finally:
        server.close()
