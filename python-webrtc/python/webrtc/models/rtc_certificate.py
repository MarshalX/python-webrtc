#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import time
from typing import Any, List, Mapping, NamedTuple, Optional, Union

import wrtc
from webrtc.base import WebRTCObject

Algorithm = Union[str, Mapping[str, Any]]


class RTCDtlsFingerprint(NamedTuple):
    """A fingerprint of a certificate, as in the ``a=fingerprint`` line of SDP."""

    #: :obj:`str`: The hash function, like ``'sha-256'``.
    algorithm: str
    #: :obj:`str`: The hash in lowercase hex bytes separated with colons.
    value: str


def _member(algorithm: Mapping[str, Any], name: str, default=None):
    """A member of a WebCrypto algorithm dictionary, by its camelCase or snake_case name"""
    snake = ''.join(f'_{c.lower()}' if c.isupper() else c for c in name)
    return algorithm.get(name, algorithm.get(snake, default))


def _key_params(algorithm: Algorithm):
    """The key type, modulus length and public exponent for an algorithm, as generate_certificate takes them"""
    from webrtc import NotSupportedError

    if isinstance(algorithm, str):
        algorithm = {'name': algorithm}
    name = str(_member(algorithm, 'name', '')).upper()
    if name == 'ECDSA':
        curve = _member(algorithm, 'namedCurve', 'P-256')
        if curve != 'P-256':
            raise NotSupportedError(f'the {curve} curve is not supported, only P-256 is')
        return 'ecdsa', 0, 0
    if name == 'RSASSA-PKCS1-V1_5':
        hash_name = _member(algorithm, 'hash')
        if isinstance(hash_name, Mapping):
            hash_name = hash_name.get('name')
        modulus_length = _member(algorithm, 'modulusLength')
        exponent = _member(algorithm, 'publicExponent')
        if hash_name is None or modulus_length is None or exponent is None:
            raise NotSupportedError('RSASSA-PKCS1-v1_5 needs a hash, a modulus length and a public exponent')
        if str(hash_name).upper() != 'SHA-256':
            raise NotSupportedError(f'the {hash_name} hash is not supported, only SHA-256 is')
        if isinstance(exponent, (bytes, bytearray, memoryview)):
            exponent = int.from_bytes(bytes(exponent), 'big')
        return 'rsa', int(modulus_length), int(exponent)
    raise NotSupportedError(
        f'the {algorithm.get("name")!r} algorithm is not supported, ECDSA and RSASSA-PKCS1-v1_5 are'
    )


class RTCCertificate(WebRTCObject):
    """A certificate a connection uses to authenticate with DTLS, from :meth:`generate`, and set with
    :attr:`webrtc.RTCConfiguration.certificates`. Without one, a connection generates its own."""

    _class = wrtc.RTCCertificate

    @classmethod
    async def generate(cls, algorithm: Algorithm = 'ECDSA', expires: Optional[float] = None) -> 'RTCCertificate':
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
            :obj:`webrtc.NotSupportedError`: If the algorithm isn't supported.
            :obj:`ValueError`: If ``expires`` is negative.
        """
        from webrtc import NotSupportedError

        key_type, modulus_length, exponent = _key_params(algorithm)
        if expires is not None and expires < 0:
            raise ValueError(f'expires must not be negative, not {expires}')
        native = await asyncio.get_running_loop().run_in_executor(
            None,
            cls._class.generate,
            key_type,
            modulus_length,
            exponent,
            int(expires) if expires is not None else None,
        )
        if native is None:
            raise NotSupportedError('the key could not be generated with these parameters')
        return cls(native)

    @property
    def expires(self) -> float:
        """:obj:`float`: When the certificate expires, in milliseconds since the epoch."""
        return float(self._native_obj.expires)

    @property
    def expired(self) -> bool:
        """:obj:`bool`: Whether the certificate has expired."""
        return self.expires <= time.time() * 1000

    def get_fingerprints(self) -> List[RTCDtlsFingerprint]:
        """Returns the fingerprints of the certificate.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCDtlsFingerprint`: The fingerprints.
        """
        return [RTCDtlsFingerprint(algorithm, value) for algorithm, value in self._native_obj.fingerprints()]

    #: Alias for :attr:`get_fingerprints`
    getFingerprints = get_fingerprints
