#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""DTLS certificates of a connection and the key algorithms to generate them with."""

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
    """The lifetime of a generated certificate. It's the base of :obj:`webrtc.Algorithm`.

    See :mdn:`RTCPeerConnection/generateCertificate_static`.

    Args:
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires, capped at a year.
            It's 30 days if omitted.
    """

    expires: int | None = None


# the members are required, but expires keyword-only after them, which dataclasses can't do before 3.10
@dataclass(init=False)
class Algorithm(RTCCertificateExpiration):
    """A key algorithm by its WebCrypto name, for :meth:`webrtc.RTCPeerConnection.generate_certificate`.

    ``'ECDSA'`` uses the P-256 curve. ``'RSASSA-PKCS1-v1_5'`` needs an :obj:`webrtc.RsaHashedKeyGenParams` instead.

    Args:
        name (:obj:`str`): The name, like ``'ECDSA'``, compared case-insensitively.
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires (keyword-only).
    """

    name: str

    def __init__(self, name: str, *, expires: int | None = None) -> None:
        super().__init__(expires)
        self.name = name


@dataclass(init=False)
class EcKeyGenParams(Algorithm):
    """An ECDSA key algorithm with an explicit curve.

    See :mdn:`EcKeyGenParams`.

    Args:
        name (:obj:`str`): ``'ECDSA'``.
        named_curve (:obj:`str`): The curve, of which only ``'P-256'`` is supported.
        expires (:obj:`int`, optional): In how many milliseconds the certificate expires (keyword-only).
    """

    named_curve: str

    def __init__(self, name: str, named_curve: str, *, expires: int | None = None) -> None:
        super().__init__(name, expires=expires)
        self.named_curve = named_curve

    #: Alias for :attr:`named_curve`
    namedCurve: ClassVar[Alias[str]] = alias('named_curve')


@dataclass(init=False)
class RsaHashedKeyGenParams(Algorithm):
    """An RSA key algorithm. Every member but the name is keyword-only.

    See :mdn:`RsaHashedKeyGenParams`.

    Args:
        name (:obj:`str`): ``'RSASSA-PKCS1-v1_5'``.
        modulus_length (:obj:`int`): The length of the modulus in bits, like 2048.
        public_exponent (:obj:`bytes`): The public exponent, big-endian, like ``bytes([1, 0, 1])`` for 65537.
        hash (:obj:`str` or :obj:`webrtc.Algorithm`): The hash function, of which only ``'SHA-256'`` is supported.
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


#: A key algorithm, or its name (like ``'ECDSA'``), as :meth:`webrtc.RTCPeerConnection.generate_certificate` takes it
AlgorithmIdentifier = Union[str, Algorithm]


@dataclass(frozen=True)
class RTCDtlsFingerprint(Dictionary):
    """A fingerprint of a certificate, as the ``a=fingerprint`` line of SDP carries it. It's immutable.

    See :mdn:`RTCCertificate/getFingerprints`.

    Args:
        algorithm (:obj:`str`, optional): The hash function, like ``'sha-256'``.
        value (:obj:`str`, optional): The hash as lowercase hex bytes separated with colons.
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
    """A certificate and its private key, which a connection authenticates with in DTLS.

    Only :meth:`webrtc.RTCPeerConnection.generate_certificate` creates it, and a connection uses it through
    :attr:`webrtc.RTCConfiguration.certificates`. A connection without one generates its own.
    See :mdn:`RTCCertificate`.
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
        """:obj:`float`: When the certificate expires, in milliseconds since the Unix epoch.

        A configuration with an expired certificate raises :obj:`webrtc.InvalidAccessError`.
        See :mdn:`RTCCertificate/expires`.
        """
        return float(self._native_obj.expires)

    def _expired(self) -> bool:
        return self.expires <= time.time() * 1000

    def get_fingerprints(self) -> list[RTCDtlsFingerprint]:
        """Returns the fingerprints of the certificate, as the remote peer sees them in the SDP.

        See :mdn:`RTCCertificate/getFingerprints`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCDtlsFingerprint`: The fingerprints.
        """
        return list(starmap(RTCDtlsFingerprint, self._native_obj.fingerprints()))

    #: Alias for :attr:`get_fingerprints`
    getFingerprints = get_fingerprints
