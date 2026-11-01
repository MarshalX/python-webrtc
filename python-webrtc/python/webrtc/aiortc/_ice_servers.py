# Copied from aiortc 1.15.0 (src/aiortc/rtcicetransport.py), its STUN and TURN URL helpers only.
#
# Copyright (c) Jeremy Lainé.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of aiortc nor the names of its contributors may
#       be used to endorse or promote products derived from this software without
#       specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import re
from typing import Any

from .rtcconfiguration import RTCIceServer

# See https://datatracker.ietf.org/doc/html/rfc7064
# transport is not defined by RFC 7064 and rejected by browsers.
STUN_REGEX = re.compile(
    r"(?P<scheme>stun|stuns)\:(?P<host>[^?:]+)(\:(?P<port>[0-9]+?))?"
    r"(\?transport=(?P<transport>.*))?"
)
# See https://datatracker.ietf.org/doc/html/rfc7065
TURN_REGEX = re.compile(
    r"(?P<scheme>turn|turns)\:(?P<host>[^?:]+)(\:(?P<port>[0-9]+?))?"
    r"(\?transport=(?P<transport>.*))?"
)


def connection_kwargs(servers: list[RTCIceServer]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    for server in servers:
        if isinstance(server.urls, list):
            uris = server.urls
        else:
            uris = [server.urls]

        for uri in uris:
            parsed = parse_stun_turn_uri(uri)

            if parsed["scheme"] == "stun":
                # only a single STUN server is supported
                if "stun_server" in kwargs:
                    continue

                kwargs["stun_server"] = (parsed["host"], parsed["port"])
            elif parsed["scheme"] in ["turn", "turns"]:
                # only a single TURN server is supported
                if "turn_server" in kwargs:
                    continue

                # only 'udp' and 'tcp' transports are supported
                if parsed["scheme"] == "turn" and parsed["transport"] not in [
                    "udp",
                    "tcp",
                ]:
                    continue
                elif parsed["scheme"] == "turns" and parsed["transport"] != "tcp":
                    continue

                # only 'password' credentialType is supported
                if server.credentialType != "password":
                    continue

                kwargs["turn_server"] = (parsed["host"], parsed["port"])
                kwargs["turn_ssl"] = parsed["scheme"] == "turns"
                kwargs["turn_transport"] = parsed["transport"]
                kwargs["turn_username"] = server.username
                kwargs["turn_password"] = server.credential

    return kwargs


def parse_stun_turn_uri(uri: str) -> dict[str, Any]:
    if uri.startswith("stun"):
        match = STUN_REGEX.fullmatch(uri)
    elif uri.startswith("turn"):
        match = TURN_REGEX.fullmatch(uri)
    else:
        raise ValueError("malformed uri: invalid scheme")

    if not match:
        raise ValueError("malformed uri")

    # set port
    parsed: dict[str, Any] = match.groupdict()
    if parsed["port"]:
        parsed["port"] = int(parsed["port"])
    elif parsed["scheme"] in ["stuns", "turns"]:
        parsed["port"] = 5349
    else:
        parsed["port"] = 3478

    # set transport
    if parsed["scheme"] == "turn" and not parsed["transport"]:
        parsed["transport"] = "udp"
    elif parsed["scheme"] == "turns" and not parsed["transport"]:
        parsed["transport"] = "tcp"
    elif parsed["scheme"] in ["stun", "stuns"]:
        if parsed["transport"] is not None:
            raise ValueError(
                "malformed uri: " + parsed["scheme"] + " must not contain transport"
            )
        del parsed["transport"]

    return parsed
