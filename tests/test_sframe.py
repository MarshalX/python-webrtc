#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""SFrame of WebRTC Encoded Transform: RFC 9605 vectors, the streams, and the transforms of a real connection."""

from __future__ import annotations

import asyncio
import contextlib
import gc
from typing import TYPE_CHECKING, NamedTuple, Union

import pytest

import webrtc
import wrtc
from tests.helpers import connect, mistyped, settled_alive, wait_until

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Buffer

TIMEOUT = 15
SUITES = list(webrtc.SFrameCipherSuite)
KEY = bytes(range(16))
OTHER_KEY = bytes(range(1, 17))

Frame = Union[webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame]


class Vector(NamedTuple):
    cipher_suite: int
    sframe_key: str
    sframe_salt: str
    nonce: str
    ct: str


# RFC 9605 Appendix C.4 (suites 1 to 5) and draft-barnes-sframe-iana-256 Appendix A.2 (6 to 8): KID 0x123,
# CTR 0x4567 and the same base key, metadata and plaintext
VECTORS = [
    Vector(
        1,
        '3f7d9a7c83ae8e1c8a11ae695ab59314b367e359fadac7b9c46b2bc6f81f46e16b96f0811868d59402b7e870102720b3',
        '50b29329a04dc0f184ac3168',
        '50b29329a04dc0f184ac740f',
        '9901234567449408b6f490086165b9d6f62b24ae1a59a56486b4ae8ed036b88912e24f11',
    ),
    Vector(
        2,
        'e2ec5c797540310483b16bf6e7a570d2a27d192fe869c7ccd8584a8d9dab91549fbe553f5113461ec6aa83bf3865553e',
        'e68ac8dd3d02fbcd368c5577',
        'e68ac8dd3d02fbcd368c1010',
        '99012345673f31438db4d09434e43afa0f8a2f00867a2be085046a9f5cb4f101d607',
    ),
    Vector(
        3,
        '2c5703089cbb8c583475e4fc461d97d18809df79b6d550f78eb6d50ffa80d89211d57909934f46f5405e38cd583c69fe',
        '38c16e4f5159700c00c7f350',
        '38c16e4f5159700c00c7b637',
        '990123456717fc8af28a5a695afcfc6c8df6358a17e26b2fcb3bae32e443',
    ),
    Vector(
        4,
        'd34f547f4ca4f9a7447006fe7fcbf768',
        '75234edefe07819026751816',
        '75234edefe07819026755d71',
        '9901234567b7412c2513a1b66dbb48841bbaf17f598751176ad847681a69c6d0b091c07018ce4adb34eb',
    ),
    Vector(
        5,
        'd3e27b0d4a5ae9e55df01a70e6d4d28d969b246e2936f4b7a5d9b494da6b9633',
        '84991c167b8cd23c93708ec7',
        '84991c167b8cd23c9370cba0',
        '990123456794f509d36e9beacb0e261d99c7d1e972f1fed787d4049f17ca21353c1cc24d56ceabced279',
    ),
    Vector(
        6,
        '3c343886ec1c79278836863e00fe934c8894460cfa367ebdc4856b0a9268a4f4fb99437876819394ef90b10ee12602d0'
        '23f7128ee50f2314c2cc3cff4c56616d2fe03ad2a254cc2ed29b2a4d3f2534c0dda9e7c391ad1917ea07aa221dd4b224',
        'e082f7ce012ad30c87c49e3f',
        'e082f7ce012ad30c87c4db58',
        '9901234567b369e03ec6467ad505ddc84914115069280c5c797555be6e32cde6ac25bc9e',
    ),
    Vector(
        7,
        '7271d6c6cbccd2e2343d480ebea65718a7bb379eefcf3f8d107c1e2a76e755293a497fd9e4e8291b965161987ef4ef24'
        '983eabb06cb0a392defaab18654780a39c106ffa4a47d4183a6e593cd0c1bcab2b9c6dcf049215845bfb7580c4dea80e',
        '46b4367993a314910d4d9f3d',
        '46b4367993a314910d4dda5a',
        '990123456797cb5644d8831ff8bdc080249990b24b569144cab2a87be22c20d97976',
    ),
    Vector(
        8,
        'afe92c81e0df8c00fab619e0559fe5aeefce1ef77789d4c728af1b1c1f2e3552c405d274415a5291ec075c2d9954c450'
        'fbd36682a4e978494808b703ce78b409f9fec29b91e6e703a75c4131377c80c9d51b8906088092452e2593eb142eea2d',
        'f6de647bac1263524cfb6533',
        'f6de647bac1263524cfb2054',
        '9901234567112a94a288b85b49ffef1d279f2830165c39d76cac8884011c',
    ),
]
VECTOR_KID = 0x123
VECTOR_CTR = 0x4567
VECTOR_BASE_KEY = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
VECTOR_METADATA = bytes.fromhex('4945544620534672616d65205747')
VECTOR_PT = bytes.fromhex('64726166742d696574662d736672616d652d656e63')

# RFC 9605 Appendix C.1, a sample of each size of KID and CTR
HEADERS = [
    (0, 0, '00'),
    (0, 7, '07'),
    (0, 255, '08ff'),
    (0, 256, '090100'),
    (0, 0xFFFFFFFFFFFFFFFF, '0fffffffffffffffff'),
    (1, 0, '10'),
    (1, 65536, '1a010000'),
    (255, 1, '81ff'),
    (255, 72057594037927935, '8effffffffffffffff'),
    (256, 256, '9901000100'),
    (65535, 16777216, '9bffff01000000'),
    (65536, 4294967296, 'ac0100000100000000'),
    (16777215, 0, 'a0ffffff'),
    (4294967296, 1099511627775, 'cc0100000000ffffffffff'),
    (281474976710656, 281474976710655, 'ed01000000000000ffffffffffff'),
    (72057594037927936, 72057594037927936, 'ff01000000000000000100000000000000'),
    (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 'ffffffffffffffffffffffffffffffffff'),
]


@pytest.mark.parametrize('vector', VECTORS, ids=[f'suite-{v.cipher_suite}' for v in VECTORS])
def test_rfc_vectors(vector: Vector) -> None:
    key, salt = wrtc._sframeDerive(vector.cipher_suite, VECTOR_BASE_KEY, VECTOR_KID)
    assert key.hex() == vector.sframe_key
    assert salt.hex() == vector.sframe_salt
    # nonce = salt XOR CTR
    nonce = bytes(a ^ b for a, b in zip(salt, VECTOR_CTR.to_bytes(12, 'big')))
    assert nonce.hex() == vector.nonce

    ciphertext = wrtc._sframeEncrypt(
        vector.cipher_suite, VECTOR_BASE_KEY, VECTOR_KID, VECTOR_CTR, VECTOR_METADATA, VECTOR_PT
    )
    assert ciphertext.hex() == vector.ct
    assert wrtc._sframeDecrypt(vector.cipher_suite, VECTOR_BASE_KEY, VECTOR_METADATA, bytes.fromhex(vector.ct)) == (
        VECTOR_PT
    )
    assert wrtc._sframeDecrypt(vector.cipher_suite, VECTOR_BASE_KEY, b'', bytes.fromhex(vector.ct)) is None
    tampered = bytearray.fromhex(vector.ct)
    tampered[-1] ^= 1
    assert wrtc._sframeDecrypt(vector.cipher_suite, VECTOR_BASE_KEY, VECTOR_METADATA, tampered) is None


@pytest.mark.parametrize(('kid', 'ctr', 'encoded'), HEADERS)
def test_rfc_headers(kid: int, ctr: int, encoded: str) -> None:
    assert wrtc._sframeHeader(kid, ctr).hex() == encoded
    assert wrtc._sframeParseHeader(bytes.fromhex(encoded) + b'payload') == (kid, ctr, len(encoded) // 2)


def test_truncated_headers() -> None:
    assert wrtc._sframeParseHeader(b'') is None
    assert wrtc._sframeParseHeader(bytes.fromhex('9901')) is None
    assert wrtc._sframeParseHeader(bytes.fromhex('0f01')) is None


def test_the_suites_are_numbered_like_rfc() -> None:
    names = [suite.value for suite in webrtc.SFrameCipherSuite]
    assert names == [
        'AES_128_CTR_HMAC_SHA256_80',
        'AES_128_CTR_HMAC_SHA256_64',
        'AES_128_CTR_HMAC_SHA256_32',
        'AES_128_GCM_SHA256_128',
        'AES_256_GCM_SHA512_128',
        'AES_256_CTR_HMAC_SHA512_80',
        'AES_256_CTR_HMAC_SHA512_64',
        'AES_256_CTR_HMAC_SHA512_32',
    ]


class Errors:
    """Records the error events of a decryptor."""

    def __init__(self, target: webrtc.RTCRtpSFrameDecryptor | webrtc.SFrameDecryptorStream) -> None:
        self.events: list[webrtc.SFrameTransformErrorEvent] = []
        self._waiters: list[asyncio.Future[None]] = []
        target.on('error', self._on_error)

    def _on_error(self, event: webrtc.SFrameTransformErrorEvent) -> None:
        self.events.append(event)
        for waiter in self._waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def wait(self) -> webrtc.SFrameTransformErrorEvent:
        if len(self.events) == 0:
            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            await asyncio.wait_for(waiter, TIMEOUT)
        return self.events[-1]

    async def wait_for(self, error_type: webrtc.SFrameTransformErrorEventType, key_id: int) -> None:
        """Waits for an error of a type and key id, as errors of frames sent before a key change may come first."""
        await wait_until(
            lambda: any(e.error_type == error_type and e.key_id == key_id for e in self.events),
            f'a {error_type.value} error of key {key_id}',
            TIMEOUT,
        )


def options(suite: webrtc.SFrameCipherSuite) -> webrtc.SFrameTransformOptions:
    return webrtc.SFrameTransformOptions(suite)


async def through(stream: webrtc.SFrameEncryptorStream | webrtc.SFrameDecryptorStream, chunk: Buffer) -> object:
    """Writes a chunk and reads what comes out."""
    writer = stream.writable.get_writer()
    reader = stream.readable.get_reader()
    try:
        written = writer.write(chunk)
        result = await asyncio.wait_for(reader.read(), TIMEOUT)
        await written
        return result.value
    finally:
        writer.release_lock()
        reader.release_lock()


@pytest.mark.asyncio
@pytest.mark.parametrize('suite', SUITES)
async def test_streams_round_trip(suite: webrtc.SFrameCipherSuite) -> None:
    encryptor = webrtc.SFrameEncryptorStream(options(suite))
    decryptor = webrtc.SFrameDecryptorStream(options(suite))
    await encryptor.set_encryption_key(KEY, 300)
    await decryptor.add_decryption_key(KEY, 300)
    errors = Errors(decryptor)

    plaintexts = [b'', b'x', bytes(range(256)) * 40]
    for counter, plaintext in enumerate(plaintexts):
        ciphertext = await through(encryptor, plaintext)
        assert isinstance(ciphertext, bytes)
        header = wrtc._sframeParseHeader(ciphertext)
        assert header is not None
        assert header[:2] == (300, counter)
        assert ciphertext[header[2] : header[2] + len(plaintext)] != plaintext or len(plaintext) == 0
        assert await through(decryptor, ciphertext) == plaintext
    assert errors.events == []


@pytest.mark.asyncio
async def test_streams_take_any_buffer() -> None:
    """Like WPT sframe-transform-buffer-source: views of the same bytes encrypt the same."""
    results: list[object] = []
    data = bytes(range(10))
    padded = bytearray(11)
    padded[1:] = data
    for chunk in (data, bytearray(data), memoryview(padded)[1:]):
        stream = webrtc.SFrameEncryptorStream(options(webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_80))
        await stream.set_encryption_key(KEY, 0)
        results.append(await through(stream, chunk))
    assert results[0] == results[1] == results[2]


@pytest.mark.asyncio
async def test_stream_errors_on_other_chunks() -> None:
    stream = webrtc.SFrameDecryptorStream(options(webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128))
    writer = stream.writable.get_writer()
    # a pending read relieves the backpressure of the readable side
    read = asyncio.ensure_future(stream.readable.get_reader().read())
    with pytest.raises(TypeError):
        await writer.write(mistyped({}))
    with pytest.raises(TypeError):
        await writer.closed
    with pytest.raises(TypeError):
        await read


@pytest.mark.asyncio
async def test_encryptor_stream_without_a_key_drops() -> None:
    stream = webrtc.SFrameEncryptorStream(options(webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(through(stream, b'clear'), 0.3)


class Probe:
    """Writes to a decryptor stream with a read pending, which relieves backpressure and only plaintext fulfills."""

    def __init__(self, decryptor: webrtc.SFrameDecryptorStream) -> None:
        self.errors = Errors(decryptor)
        self.writer = decryptor.writable.get_writer()
        self.reader = decryptor.readable.get_reader()
        self.read = asyncio.ensure_future(self.reader.read())

    async def error_of(self, chunk: bytes) -> webrtc.SFrameTransformErrorEvent:
        self.errors.events.clear()
        await self.writer.write(chunk)
        return await self.errors.wait()

    async def plaintext_of(self, chunk: bytes) -> object:
        await self.writer.write(chunk)
        result = await asyncio.wait_for(self.read, TIMEOUT)
        self.read = asyncio.ensure_future(self.reader.read())
        return result.value


async def sealed(suite: webrtc.SFrameCipherSuite, key_id: int, plaintext: bytes) -> bytes:
    encryptor = webrtc.SFrameEncryptorStream(options(suite))
    await encryptor.set_encryption_key(KEY, key_id)
    ciphertext = await through(encryptor, plaintext)
    assert isinstance(ciphertext, bytes)
    return ciphertext


@pytest.mark.asyncio
async def test_decryptor_stream_errors() -> None:
    suite = webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_32
    ciphertext = await sealed(suite, 7, b'secret')
    decryptor = webrtc.SFrameDecryptorStream(options(suite))
    probe = Probe(decryptor)

    event = await probe.error_of(ciphertext)
    assert event.error_type == webrtc.SFrameTransformErrorEventType.key_id
    assert event.errorType == 'keyID'
    assert event.key_id == 7
    assert event.keyID == 7
    assert event.frame == ciphertext
    assert event.target == decryptor

    await decryptor.add_decryption_key(OTHER_KEY, 7)
    event = await probe.error_of(ciphertext)
    assert event.error_type == webrtc.SFrameTransformErrorEventType.authentication
    assert event.key_id is None

    for chunk in (b'', bytes.fromhex('9901'), ciphertext[:4]):
        event = await probe.error_of(chunk)
        assert event.error_type == webrtc.SFrameTransformErrorEventType.syntax
    assert not probe.read.done()
    probe.read.cancel()


@pytest.mark.asyncio
async def test_decryptor_stream_keys() -> None:
    suite = webrtc.SFrameCipherSuite.AES_256_GCM_SHA512_128
    ciphertext = await sealed(suite, 2**64 - 1, b'secret')
    decryptor = webrtc.SFrameDecryptorStream(options(suite))
    probe = Probe(decryptor)

    await decryptor.add_decryption_key(OTHER_KEY, 2**64 - 1)
    event = await probe.error_of(ciphertext)
    assert event.error_type == webrtc.SFrameTransformErrorEventType.authentication
    await decryptor.add_decryption_key(KEY, 2**64 - 1)
    assert await probe.plaintext_of(ciphertext) == b'secret'
    await decryptor.remove_decryption_key(2**64 - 1)
    event = await probe.error_of(ciphertext)
    assert event.error_type == webrtc.SFrameTransformErrorEventType.key_id
    assert event.key_id == 2**64 - 1
    probe.read.cancel()


@pytest.mark.asyncio
async def test_key_validation() -> None:
    encryptor = webrtc.SFrameEncryptorStream(options(webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128))
    decryptor = webrtc.RTCRtpSFrameDecryptor(options(webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128))
    for key_id in (0, 1, 2**64 - 1):
        await encryptor.setEncryptionKey(KEY, key_id)
        await decryptor.addDecryptionKey(KEY, key_id)
        await decryptor.removeDecryptionKey(key_id)
    for key_id in (-1, 2**64):
        with pytest.raises(webrtc.InvalidRangeError, match='Not a 64 bits integer'):
            await encryptor.set_encryption_key(KEY, key_id)
        with pytest.raises(webrtc.InvalidRangeError):
            await decryptor.add_decryption_key(KEY, key_id)
        with pytest.raises(webrtc.InvalidRangeError):
            await decryptor.remove_decryption_key(key_id)
    for key_id in ('1', 1.0, True, None):
        with pytest.raises(TypeError):
            await encryptor.set_encryption_key(KEY, mistyped(key_id))
        with pytest.raises(TypeError):
            await decryptor.remove_decryption_key(mistyped(key_id))
    for key in ('key', 1, None):
        with pytest.raises(TypeError):
            await encryptor.set_encryption_key(mistyped(key), 1)
        with pytest.raises(TypeError):
            await decryptor.add_decryption_key(mistyped(key), 1)
    # any length: the base key of RFC 9605 is the input of HKDF
    await encryptor.set_encryption_key(b'', 1)
    await encryptor.set_encryption_key(bytes(100), 1)


def test_options() -> None:
    assert webrtc.RTCRtpSFrameEncryptorOptions('AES_128_GCM_SHA256_128').type == webrtc.SFrameType.per_frame
    assert webrtc.SFrameTransformOptions('AES_256_GCM_SHA512_128').cipherSuite == 'AES_256_GCM_SHA512_128'
    assert webrtc.SFrameTransformOptions.from_json({'cipherSuite': 'AES_128_CTR_HMAC_SHA256_32'}).cipher_suite == (
        webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_32
    )
    with pytest.raises(ValueError, match='AES_512'):
        webrtc.SFrameTransformOptions(mistyped('AES_512'))
    with pytest.raises(ValueError, match='per-byte'):
        webrtc.RTCRtpSFrameEncryptorOptions('AES_128_GCM_SHA256_128', mistyped('per-byte'))
    with pytest.raises(TypeError):
        webrtc.RTCRtpSFrameEncryptor(mistyped({'cipherSuite': 'AES_128_GCM_SHA256_128'}))
    with pytest.raises(webrtc.NotSupportedError):
        webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions('AES_128_GCM_SHA256_128', 'per-packet'))


def test_error_event() -> None:
    frame = b'\x00'
    event = webrtc.SFrameTransformErrorEvent('error', webrtc.SFrameTransformErrorEventInit('keyID', frame, key_id=5))
    assert event.type == 'error'
    assert event.error_type == webrtc.SFrameTransformErrorEventType.key_id
    assert event.key_id == 5
    assert event.frame is frame


@pytest.fixture
def pair() -> Iterator[tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]]:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    yield caller, callee
    caller.close()
    callee.close()


async def local_track(kind: str) -> webrtc.MediaStreamTrack:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(**{kind: True}))
    return stream.get_tracks()[0]


async def encrypted_call(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    kind: str,
    *,
    encryptor: webrtc.RTCRtpSFrameEncryptor,
    receiver_transform: webrtc.RTCRtpSFrameDecryptor | webrtc.RTCRtpScriptTransform,
) -> tuple[webrtc.RTCRtpSender, webrtc.RTCRtpReceiver]:
    """Sends a track with transforms set before negotiation, and connects."""
    sender = caller.add_track(await local_track(kind))
    sender.transform = encryptor
    receivers: list[webrtc.RTCRtpReceiver] = []

    def on_track(event: webrtc.RTCTrackEvent) -> None:
        receivers.append(event.receiver)
        event.receiver.transform = receiver_transform

    callee.on('track', on_track)
    await connect(caller, callee)
    assert len(receivers) == 1
    return sender, receivers[0]


async def read_media(track: webrtc.MediaStreamTrack, count: int) -> list[object]:
    """Reads decoded frames (or audio data) of a remote track."""
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=10))
    reader = processor.readable.get_reader()
    chunks: list[object] = []
    try:
        while len(chunks) < count:
            chunk = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
            assert isinstance(chunk, (webrtc.VideoFrame, webrtc.AudioData))
            chunks.append(chunk)
            chunk.close()
    finally:
        await reader.cancel()
    return chunks


def sframe_pair(
    suite: webrtc.SFrameCipherSuite = webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128,
) -> tuple[webrtc.RTCRtpSFrameEncryptor, webrtc.RTCRtpSFrameDecryptor]:
    return (
        webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(suite)),
        webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(suite)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kind', 'suite'),
    [
        ('video', webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_80),
        ('video', webrtc.SFrameCipherSuite.AES_256_GCM_SHA512_128),
        ('audio', webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128),
        ('audio', webrtc.SFrameCipherSuite.AES_256_CTR_HMAC_SHA512_32),
    ],
)
async def test_media_flows_encrypted(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection], kind: str, suite: webrtc.SFrameCipherSuite
) -> None:
    caller, callee = pair
    encryptor, decryptor = sframe_pair(suite)
    await encryptor.set_encryption_key(KEY, 1)
    await decryptor.add_decryption_key(KEY, 1)
    errors = Errors(decryptor)
    sender, receiver = await encrypted_call(caller, callee, kind, encryptor=encryptor, receiver_transform=decryptor)

    assert sender.transform == encryptor
    assert isinstance(sender.transform, webrtc.RTCRtpSFrameEncryptor)
    assert receiver.transform == decryptor
    assert isinstance(receiver.transform, webrtc.RTCRtpSFrameDecryptor)
    await read_media(receiver.track, 20)
    assert errors.events == []


class Inspector:
    """A receiver worker reading the SFrame frames on the wire, and decrypting them with a decryptor stream."""

    def __init__(self, suite: webrtc.SFrameCipherSuite) -> None:
        self.decryptor = webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions(suite))
        self.headers: list[tuple[int, int, int]] = []
        self.done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def record(self, frame: Frame, controller: webrtc.TransformStreamDefaultController[Frame, Frame]) -> None:
        header = wrtc._sframeParseHeader(frame.data)
        assert header is not None
        self.headers.append(header)
        controller.enqueue(frame)

    async def __call__(self, event: webrtc.RTCTransformEvent) -> None:
        transformer = event.transformer
        inspect: webrtc.TransformStream[Frame, Frame] = webrtc.TransformStream({'transform': self.record})
        with contextlib.suppress(Exception):
            decrypted = transformer.readable.pipe_through(inspect).pipe_through(self.decryptor)
            await decrypted.pipe_to(transformer.writable)
        self.done.set_result(None)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['video', 'audio'])
async def test_frames_are_encrypted_on_the_wire(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection], kind: str
) -> None:
    """Like WPT sframe-transform-in-worker: the receiver decrypts with a stream in its script transform."""
    caller, callee = pair
    suite = webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_64
    encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(suite))
    await encryptor.set_encryption_key(KEY, 9)
    inspector = Inspector(suite)
    await inspector.decryptor.add_decryption_key(KEY, 9)
    errors = Errors(inspector.decryptor)
    _, receiver = await encrypted_call(
        caller, callee, kind, encryptor=encryptor, receiver_transform=webrtc.RTCRtpScriptTransform(inspector)
    )
    await read_media(receiver.track, 10)
    # audio playout conceals missing packets, so decoded audio doesn't mean frames arrived yet
    await wait_until(lambda: len({counter for _, counter, _ in inspector.headers}) >= 5, 'five frames', TIMEOUT)

    assert all(key_id == 9 for key_id, _, _ in inspector.headers)
    # retransmitted packets may assemble a received frame again, out of order
    assert len({counter for _, counter, _ in inspector.headers}) >= 5
    assert errors.events == []


@pytest.mark.asyncio
async def test_decryption_errors(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    encryptor, decryptor = sframe_pair()
    await encryptor.set_encryption_key(KEY, 1)
    await decryptor.add_decryption_key(OTHER_KEY, 1)
    errors = Errors(decryptor)
    sender, receiver = await encrypted_call(caller, callee, 'video', encryptor=encryptor, receiver_transform=decryptor)

    event = await errors.wait()
    assert event.error_type == webrtc.SFrameTransformErrorEventType.authentication
    assert event.key_id is None
    assert isinstance(event.frame, webrtc.RTCEncodedVideoFrame)
    assert event.frame.get_metadata().synchronization_source is not None
    assert event.target == decryptor

    await encryptor.set_encryption_key(KEY, 2**64 - 1)
    await errors.wait_for(webrtc.SFrameTransformErrorEventType.key_id, 2**64 - 1)

    await decryptor.add_decryption_key(KEY, 2**64 - 1)
    await read_media(receiver.track, 5)
    assert sender.transform == encryptor


@pytest.mark.asyncio
async def test_key_rotation(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    encryptor, decryptor = sframe_pair(webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_80)
    await encryptor.set_encryption_key(KEY, 1)
    await decryptor.add_decryption_key(KEY, 1)
    await decryptor.add_decryption_key(OTHER_KEY, 2)
    errors = Errors(decryptor)
    _, receiver = await encrypted_call(caller, callee, 'audio', encryptor=encryptor, receiver_transform=decryptor)
    await read_media(receiver.track, 10)

    await encryptor.set_encryption_key(OTHER_KEY, 2)
    await decryptor.remove_decryption_key(1)
    await read_media(receiver.track, 10)
    # only frames sent before the key change may fail, with the key removed
    key_id = webrtc.SFrameTransformErrorEventType.key_id
    assert all(e.error_type == key_id and e.key_id == 1 for e in errors.events)

    await decryptor.remove_decryption_key(2)
    await errors.wait_for(key_id, 2)
    assert all(isinstance(e.frame, webrtc.RTCEncodedAudioFrame) for e in errors.events)


@pytest.mark.asyncio
async def test_encryptor_without_a_key_sends_nothing(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    caller, callee = pair
    encryptor, decryptor = sframe_pair()
    await decryptor.add_decryption_key(KEY, 0)
    errors = Errors(decryptor)
    _, receiver = await encrypted_call(caller, callee, 'audio', encryptor=encryptor, receiver_transform=decryptor)
    await asyncio.sleep(1)
    assert errors.events == []
    assert receiver.track.muted

    await encryptor.set_encryption_key(KEY, 0)
    await read_media(receiver.track, 5)


def test_transform_attribute_types(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    """Like WPT sframe-transform: an encryptor is for a sender, a decryptor for a receiver, each for one."""
    caller, _ = pair
    encryptor, decryptor = sframe_pair()
    audio = caller.add_transceiver('audio')
    video = caller.add_transceiver('video')
    with pytest.raises(TypeError):
        audio.sender.transform = mistyped(decryptor)
    with pytest.raises(TypeError):
        audio.receiver.transform = mistyped(encryptor)
    with pytest.raises(TypeError):
        audio.sender.transform = mistyped(
            webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128'))
        )

    audio.sender.transform = encryptor
    audio.receiver.transform = decryptor
    with pytest.raises(webrtc.InvalidStateError):
        video.sender.transform = encryptor
    with pytest.raises(webrtc.InvalidStateError):
        video.receiver.transform = decryptor
    audio.sender.transform = encryptor
    audio.receiver.transform = decryptor
    assert audio.sender.transform == encryptor
    assert audio.receiver.transform == decryptor
    audio.sender.transform = None
    audio.receiver.transform = None
    assert audio.sender.transform is None
    assert audio.receiver.transform is None


def released_to(baseline: int) -> bool:
    """Whether the native SFrame transforms are back to the baseline, polled without blocking the loop."""
    gc.collect()
    return wrtc._alive()['SFrameTransform'] <= baseline


def alive_transforms() -> int:
    """The native SFrame transforms alive, once releases on helper threads are done."""
    return settled_alive()[0]['SFrameTransform']


@pytest.mark.asyncio
async def test_closing_releases_transforms() -> None:
    baseline = alive_transforms()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        encryptor, decryptor = sframe_pair()
        await encryptor.set_encryption_key(KEY, 1)
        await decryptor.add_decryption_key(OTHER_KEY, 1)
        errors = Errors(decryptor)
        await encrypted_call(caller, callee, 'video', encryptor=encryptor, receiver_transform=decryptor)
        await errors.wait()
        # the right key stops the errors, which every frame makes
        await decryptor.add_decryption_key(KEY, 1)
        stream = webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128'))
        Errors(stream)
        caller.close()
        callee.close()

    await session()
    await wait_until(lambda: released_to(baseline), 'the transforms released', TIMEOUT)
