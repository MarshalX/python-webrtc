#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Certificates of DTLS."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from itertools import starmap
from typing import ClassVar, Union

from webrtc import NotSupportedError, WebRTCObject, wrtc
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias


@dataclass
class RTCCertificateExpiration(Dictionary):
    """When a generated certificate expires, a member of the algorithm it's generated with.

    Args:
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires, at most a year
            (the default is 30 days).
    """

    expires: int | None = None


# the members are required, but expires keyword-only after them, which dataclasses can't do before 3.10
@dataclass(init=False)
class Algorithm(RTCCertificateExpiration):
    """A WebCrypto algorithm, by its name, for :meth:`webrtc.RTCPeerConnection.generate_certificate`.

    Args:
        name (:obj:`str`): The name, like ``'ECDSA'``.
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires.
    """

    name: str

    def __init__(self, name: str, *, expires: int | None = None) -> None:
        super().__init__(expires)
        self.name = name


@dataclass(init=False)
class EcKeyGenParams(Algorithm):
    """A WebCrypto algorithm of an elliptic curve key.

    Args:
        name (:obj:`str`): ``'ECDSA'``.
        named_curve (:obj:`str`): The curve, ``'P-256'`` as the only one supported.
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires.
    """

    named_curve: str

    def __init__(self, name: str, named_curve: str, *, expires: int | None = None) -> None:
        super().__init__(name, expires=expires)
        self.named_curve = named_curve

    #: Alias for :attr:`named_curve`
    namedCurve: ClassVar[Alias[str]] = alias('named_curve')


@dataclass(init=False)
class RsaHashedKeyGenParams(Algorithm):
    """A WebCrypto algorithm of an RSA key.

    Args:
        name (:obj:`str`): ``'RSASSA-PKCS1-v1_5'``.
        modulus_length (:obj:`int`): The length of the modulus in bits, like 2048.
        public_exponent (:obj:`bytes`): The public exponent, big-endian, like ``bytes([1, 0, 1])`` for 65537.
        hash (:obj:`str` or :obj:`webrtc.Algorithm`): The hash function, ``'SHA-256'`` as the only one supported.
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires.
    """

    modulus_length: int
    public_exponent: bytes
    hash: str | Algorithm

    def __init__(
        self,
        name: str,
        *,
        modulus_length: int,
        public_exponent: bytes,
        hash: str | Algorithm,
        expires: int | None = None,
    ) -> None:
        super().__init__(name, expires=expires)
        self.modulus_length = modulus_length
        self.public_exponent = public_exponent
        self.hash = hash

    _dictionaries: ClassVar = {'hash': Algorithm}

    #: Alias for :attr:`modulus_length`
    modulusLength: ClassVar[Alias[int]] = alias('modulus_length')
    #: Alias for :attr:`public_exponent`
    publicExponent: ClassVar[Alias[bytes]] = alias('public_exponent')


#: A WebCrypto algorithm, or its name
AlgorithmIdentifier = Union[str, Algorithm]


@dataclass(frozen=True)
class RTCDtlsFingerprint(Dictionary):
    """A fingerprint of a certificate, as in the ``a=fingerprint`` line of SDP.

    Args:
        algorithm (:obj:`str`, optional): The hash function, like ``'sha-256'``.
        value (:obj:`str`, optional): The hash in lowercase hex bytes separated with colons.
    """

    algorithm: str | None = None
    value: str | None = None


_KeyParams = tuple[str, int, int]


def _ecdsa_params(algorithm: Algorithm) -> _KeyParams:
    curve = algorithm.named_curve if isinstance(algorithm, EcKeyGenParams) else 'P-256'
    if curve != 'P-256':
        msg = f'the {curve} curve is not supported, only P-256 is'
        raise NotSupportedError(msg)
    return 'ecdsa', 0, 0


def _rsa_params(algorithm: Algorithm) -> _KeyParams:
    if not isinstance(algorithm, RsaHashedKeyGenParams):
        msg = 'RSASSA-PKCS1-v1_5 needs an RsaHashedKeyGenParams, with a hash, a modulus length and a public exponent'
        raise NotSupportedError(msg)
    hash_name = algorithm.hash.name if isinstance(algorithm.hash, Algorithm) else algorithm.hash
    if hash_name.upper() != 'SHA-256':
        msg = f'the {hash_name} hash is not supported, only SHA-256 is'
        raise NotSupportedError(msg)
    return 'rsa', algorithm.modulus_length, int.from_bytes(bytes(algorithm.public_exponent), 'big')


_KEY_PARAMS = {'ECDSA': _ecdsa_params, 'RSASSA-PKCS1-V1_5': _rsa_params}


def _key_params(algorithm: AlgorithmIdentifier) -> _KeyParams:
    """The key parameters for an algorithm."""
    if isinstance(algorithm, str):
        algorithm = Algorithm(algorithm)
    key_params = _KEY_PARAMS.get(algorithm.name.upper())
    if key_params is None:
        msg = f'the {algorithm.name!r} algorithm is not supported, ECDSA and RSASSA-PKCS1-v1_5 are'
        raise NotSupportedError(msg)
    return key_params(algorithm)


class RTCCertificate(WebRTCObject[wrtc.RTCCertificate]):
    """A certificate a connection uses to authenticate with DTLS.

    Generated with :meth:`webrtc.RTCPeerConnection.generate_certificate` and set with
    :attr:`webrtc.RTCConfiguration.certificates`. Without one, a connection generates its own.
    """

    _class = wrtc.RTCCertificate

    @classmethod
    async def _generate(cls, algorithm: AlgorithmIdentifier) -> RTCCertificate:
        # see RTCPeerConnection.generate_certificate
        key_type, modulus_length, exponent = _key_params(algorithm)
        expires = algorithm.expires if isinstance(algorithm, Algorithm) else None
        valid = expires is None or (type(expires) is int and expires >= 0)
        if not valid:
            msg = f'expires must be an unsigned 64-bit integer, not {expires!r}'
            raise TypeError(msg)
        native = await asyncio.get_running_loop().run_in_executor(
            None, wrtc.RTCCertificate.generate, key_type, modulus_length, exponent, expires
        )
        if native is None:
            msg = 'the key could not be generated with these parameters'
            raise NotSupportedError(msg)
        return cls._wrap(native)

    @property
    def expires(self) -> float:
        """:obj:`float`: When the certificate expires, in milliseconds since the epoch."""
        return float(self._native_obj.expires)

    def _expired(self) -> bool:
        return self.expires <= time.time() * 1000

    def get_fingerprints(self) -> list[RTCDtlsFingerprint]:
        """Returns the fingerprints of the certificate.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCDtlsFingerprint`: The fingerprints.
        """
        return list(starmap(RTCDtlsFingerprint, self._native_obj.fingerprints()))

    #: Alias for :attr:`get_fingerprints`
    getFingerprints = get_fingerprints
