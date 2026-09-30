#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Certificates of DTLS."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import starmap
from typing import Union

from webrtc import NotSupportedError, WebRTCObject, wrtc
from webrtc.utils.names import snake_case

#: A WebCrypto algorithm: its name (like ``'ECDSA'``), or a dictionary with its name and parameters.
Algorithm = Union[str, Mapping[str, object]]


@dataclass(frozen=True)
class RTCDtlsFingerprint:
    """A fingerprint of a certificate, as in the ``a=fingerprint`` line of SDP.

    Args:
        algorithm (:obj:`str`): The hash function, like ``'sha-256'``.
        value (:obj:`str`): The hash in lowercase hex bytes separated with colons.
    """

    algorithm: str
    value: str


#: The key type, modulus length and public exponent, as the native generate() takes them.
_KeyParams = tuple[str, int, int]


def _member(algorithm: Mapping[str, object], name: str, default: object = None) -> object:
    """A member of a WebCrypto algorithm dictionary, by its camelCase or snake_case name."""
    return algorithm.get(name, algorithm.get(snake_case(name), default))


def _ecdsa_params(algorithm: Mapping[str, object]) -> _KeyParams:
    curve = _member(algorithm, 'namedCurve', 'P-256')
    if curve != 'P-256':
        msg = f'the {curve} curve is not supported, only P-256 is'
        raise NotSupportedError(msg)
    return 'ecdsa', 0, 0


def _rsa_params(algorithm: Mapping[str, object]) -> _KeyParams:
    hash_name = _member(algorithm, 'hash')
    if isinstance(hash_name, Mapping):
        hash_name = hash_name.get('name')
    modulus_length = _member(algorithm, 'modulusLength')
    exponent = _member(algorithm, 'publicExponent')
    if hash_name is None or modulus_length is None or exponent is None:
        msg = 'RSASSA-PKCS1-v1_5 needs a hash, a modulus length and a public exponent'
        raise NotSupportedError(msg)
    if str(hash_name).upper() != 'SHA-256':
        msg = f'the {hash_name} hash is not supported, only SHA-256 is'
        raise NotSupportedError(msg)
    if isinstance(exponent, (bytes, bytearray, memoryview)):
        exponent = int.from_bytes(bytes(exponent), 'big')
    return 'rsa', int(modulus_length), int(exponent)


_KEY_PARAMS = {'ECDSA': _ecdsa_params, 'RSASSA-PKCS1-V1_5': _rsa_params}


def _key_params(algorithm: Algorithm) -> _KeyParams:
    """The key parameters for an algorithm."""
    if isinstance(algorithm, str):
        algorithm = {'name': algorithm}
    key_params = _KEY_PARAMS.get(str(_member(algorithm, 'name', '')).upper())
    if key_params is None:
        msg = f'the {algorithm.get("name")!r} algorithm is not supported, ECDSA and RSASSA-PKCS1-v1_5 are'
        raise NotSupportedError(msg)
    return key_params(algorithm)


class RTCCertificate(WebRTCObject):
    """A certificate a connection uses to authenticate with DTLS.

    Generated with :meth:`generate` and set with :attr:`webrtc.RTCConfiguration.certificates`. Without one,
    a connection generates its own.
    """

    _class = wrtc.RTCCertificate

    @classmethod
    async def generate(cls, algorithm: Algorithm = 'ECDSA', expires: float | None = None) -> RTCCertificate:
        """Generates a key and a self-signed certificate, on a worker thread.

        Args:
            algorithm (:obj:`str` or :obj:`dict`, optional): A WebCrypto algorithm: ``'ECDSA'`` (with the P-256 curve),
                or a dictionary like ``{'name': 'RSASSA-PKCS1-v1_5', 'modulus_length': 2048,
                'public_exponent': 65537, 'hash': 'SHA-256'}``.
            expires (:obj:`float`, optional): In how many milliseconds the certificate expires, at most a year
                (the default is 30 days).

        Returns:
            :obj:`webrtc.RTCCertificate`: The certificate.

        Raises:
            webrtc.NotSupportedError: If the algorithm isn't supported.
            ValueError: If ``expires`` is negative.
        """
        key_type, modulus_length, exponent = _key_params(algorithm)
        if expires is not None and expires < 0:
            msg = f'expires must not be negative, not {expires}'
            raise ValueError(msg)
        native = await asyncio.get_running_loop().run_in_executor(
            None,
            cls._class.generate,
            key_type,
            modulus_length,
            exponent,
            int(expires) if expires is not None else None,
        )
        if native is None:
            msg = 'the key could not be generated with these parameters'
            raise NotSupportedError(msg)
        return cls._wrap(native)

    @property
    def expires(self) -> float:
        """:obj:`float`: When the certificate expires, in milliseconds since the epoch."""
        return float(self._native_obj.expires)

    @property
    def expired(self) -> bool:
        """:obj:`bool`: Whether the certificate has expired."""
        return self.expires <= time.time() * 1000

    def get_fingerprints(self) -> list[RTCDtlsFingerprint]:
        """Returns the fingerprints of the certificate.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCDtlsFingerprint`: The fingerprints.
        """
        return list(starmap(RTCDtlsFingerprint, self._native_obj.fingerprints()))

    #: Alias for :attr:`get_fingerprints`
    getFingerprints = get_fingerprints
