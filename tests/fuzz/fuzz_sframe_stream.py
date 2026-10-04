#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes SFrameEncryptorStream and SFrameDecryptorStream: keys added, removed and rotated between chunks.

Chunks are arbitrary bytes, views, ciphertexts of the encryptor written in any order or tampered, or not buffers at
all. Each chunk is read back transformed, dropped, or (for the decryptor) reported by an ``error`` event, as a model
of the keys predicts; anything else than a buffer errors the stream with TypeError.
"""

from __future__ import annotations

import asyncio
import contextlib
import pathlib
import sys
from typing import TYPE_CHECKING, Generic, TypeVar

import atheris

with atheris.instrument_imports():
    from inputs import Input

    import webrtc
    import wrtc

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from tests.helpers import mistyped

if TYPE_CHECKING:
    from typing_extensions import Buffer

# a key or key id of the wrong type, or out of 64 bits
EXPECTED = (TypeError, webrtc.InvalidRangeError, webrtc.InvalidModificationError)
SUITES = list(webrtc.SFrameCipherSuite)
MAX_U64 = 2**64 - 1
# generous: the fuzz VM stalls for seconds under load, a hang is the timeout of libFuzzer
TIMEOUT = 20
DROPPED, ERRORED = object(), object()

S = TypeVar('S', webrtc.SFrameEncryptorStream, webrtc.SFrameDecryptorStream)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
failures: list[BaseException] = []


def on_loop_exception(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
    error = context.get('exception')
    if isinstance(error, BaseException) and not isinstance(error, EXPECTED):
        failures.append(error)


loop.set_exception_handler(on_loop_exception)


class Pipe(Generic[S]):
    """A stream with a read always pending, which relieves its backpressure: only an output fulfills it."""

    def __init__(self, stream: S) -> None:
        self.stream = stream
        self.writer = stream.writable.get_writer()
        self.reader = stream.readable.get_reader()
        self.read = asyncio.ensure_future(self.reader.read())
        self.errors: list[webrtc.SFrameTransformErrorEvent] = []
        if isinstance(stream, webrtc.SFrameDecryptorStream):
            stream.on('error', self.errors.append)

    async def write(self, chunk: object) -> object:
        """What came out of a chunk: its output, DROPPED, or ERRORED."""
        try:
            await asyncio.wait_for(self.writer.write(mistyped(chunk)), TIMEOUT)
        except TypeError:
            assert isinstance(await asyncio.wait_for(self._failure(), TIMEOUT), TypeError)
            return ERRORED
        # the read fulfilled is resolved in a later turn of the loop
        for _ in range(20):
            if self.read.done():
                break
            await asyncio.sleep(0)
        if not self.read.done():
            return DROPPED
        result = self.read.result()
        assert not result.done
        self.read = asyncio.ensure_future(self.reader.read())
        return result.value

    async def _failure(self) -> BaseException | None:
        try:
            await self.read
        except TypeError as e:
            return e
        return None

    async def error(self) -> webrtc.SFrameTransformErrorEvent:
        """The error event of the chunk last dropped, queued like a task."""
        for _ in range(100):
            if len(self.errors) > 0:
                break
            await asyncio.sleep(0)
        assert len(self.errors) == 1
        event = self.errors.pop()
        assert event.target is self.stream
        assert event.type == 'error'
        return event

    def close(self) -> None:
        self.read.cancel()


def u64(inp: Input) -> int:
    if inp.flag():
        return inp.unsigned(16) & MAX_U64
    return inp.small(MAX_U64) >> (inp.small(8) * 8)


def key_id(inp: Input, known: list[int]) -> int:
    mode = inp.small(15)
    if mode == 15:
        return mistyped(inp.integer(16))
    if mode < 6 and len(known) > 0:
        return inp.choice(known)
    return u64(inp)


def key(inp: Input) -> Buffer:
    if inp.small(31) == 31:
        return mistyped(inp.choice(['key', 1, None, [1, 2]]))
    return inp.contiguous(inp.small(48))


def chunk(inp: Input) -> object:
    if inp.small(31) == 31:
        return inp.choice([None, 1, 'chunk', [1], {}])
    return inp.contiguous(inp.small(512))


class Session:
    def __init__(self, inp: Input) -> None:
        self.inp = inp
        self.suite = inp.choice(SUITES)
        self.decryptor_suite = self.suite if inp.small(7) < 7 else inp.choice(SUITES)
        self.encryptor = Pipe(webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions(self.suite)))
        self.decryptor = Pipe(webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions(self.decryptor_suite)))
        self.sending: tuple[bytes, int] | None = None
        self.counter = 0
        self.keys: dict[int, bytes] = {}
        self.sent: list[tuple[bytes, bytes, int, bytes]] = []

    async def set_key(self) -> None:
        raw, kid = key(self.inp), key_id(self.inp, list(self.keys))
        await self.encryptor.stream.set_encryption_key(raw, kid)
        self.sending = (bytes(memoryview(raw)), kid)
        if self.inp.flag():
            await self.decryptor.stream.add_decryption_key(raw, kid)
            self.keys[kid] = self.sending[0]

    async def add_key(self) -> None:
        sending: list[int] = [self.sending[1]] if self.sending is not None else []
        raw, kid = key(self.inp), key_id(self.inp, sending + list(self.keys))
        await self.decryptor.stream.add_decryption_key(raw, kid)
        self.keys[kid] = bytes(memoryview(raw))

    async def remove_key(self) -> None:
        kid = key_id(self.inp, list(self.keys))
        await self.decryptor.stream.remove_decryption_key(kid)
        self.keys.pop(kid, None)

    async def encrypt(self) -> None:
        plaintext = chunk(self.inp)
        out = await self.encryptor.write(plaintext)
        if out is ERRORED:
            self.restart_encryptor()
            return
        if self.sending is None:
            assert out is DROPPED
            return
        assert isinstance(out, bytes)
        raw, kid = self.sending
        header = wrtc._sframeParseHeader(out)
        assert header is not None
        # one counter for the encryptor, whatever the key
        assert header[:2] == (kid, self.counter)
        self.counter += 1
        self.sent.append((out, raw, kid, bytes(memoryview(mistyped(plaintext)))))

    async def decrypt_sent(self) -> None:
        if len(self.sent) == 0:
            return
        ciphertext, raw, kid, plaintext = self.inp.choice(self.sent)
        tampered = self.inp.small(3) == 3
        if tampered:
            changed = bytearray(ciphertext)
            changed[self.inp.small(len(changed) - 1)] ^= self.inp.small(254) + 1
            ciphertext = bytes(changed)
        out = await self.decryptor.write(ciphertext)
        assert out is not ERRORED
        if tampered:
            assert out is DROPPED
            await self.decryptor.error()
            return
        if kid not in self.keys:
            assert out is DROPPED
            event = await self.decryptor.error()
            assert event.error_type == webrtc.SFrameTransformErrorEventType.key_id
            assert event.key_id == kid
        elif self.keys[kid] == raw and self.suite == self.decryptor_suite:
            assert out == plaintext
        else:
            assert out is DROPPED
            event = await self.decryptor.error()
            assert event.error_type in {
                webrtc.SFrameTransformErrorEventType.authentication,
                webrtc.SFrameTransformErrorEventType.syntax,
            }
            assert event.key_id is None
            assert event.frame == ciphertext

    async def decrypt(self) -> None:
        data = chunk(self.inp)
        out = await self.decryptor.write(data)
        if out is ERRORED:
            self.restart_decryptor()
            return
        if out is not DROPPED:
            assert isinstance(out, bytes)
            assert self.decryptor.errors == []
            return
        event = await self.decryptor.error()
        assert event.frame == bytes(memoryview(mistyped(data)))
        assert (event.key_id is not None) == (event.error_type == webrtc.SFrameTransformErrorEventType.key_id)
        if event.key_id is not None:
            assert event.key_id not in self.keys

    async def burst(self) -> None:
        if self.sending is None:
            return
        plaintexts = [bytes(self.inp.contiguous(self.inp.small(64))) for _ in range(self.inp.small(6) + 1)]
        writes = [self.encryptor.writer.write(plaintext) for plaintext in plaintexts]
        outs: list[object] = []
        for _ in plaintexts:
            result = await asyncio.wait_for(self.encryptor.read, TIMEOUT)
            self.encryptor.read = asyncio.ensure_future(self.encryptor.reader.read())
            outs.append(result.value)
        await asyncio.wait_for(asyncio.gather(*writes), TIMEOUT)
        raw, kid = self.sending
        for out, plaintext in zip(outs, plaintexts):
            assert isinstance(out, bytes)
            header = wrtc._sframeParseHeader(out)
            assert header is not None
            assert header[:2] == (kid, self.counter)
            self.counter += 1
            self.sent.append((out, raw, kid, plaintext))

    def restart_encryptor(self) -> None:
        self.encryptor.close()
        self.encryptor = Pipe(webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions(self.suite)))
        self.sending = None
        self.counter = 0

    def restart_decryptor(self) -> None:
        self.decryptor.close()
        self.decryptor = Pipe(webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions(self.decryptor_suite)))
        self.keys = {}

    async def end(self) -> None:
        pipe = self.encryptor if self.inp.flag() else self.decryptor
        if self.inp.flag():
            await asyncio.wait_for(pipe.writer.close(), TIMEOUT)
            result = await asyncio.wait_for(pipe.read, TIMEOUT)
            assert result.done
        else:
            await asyncio.wait_for(pipe.writer.abort(ValueError('aborted')), TIMEOUT)
            failed = False
            try:
                await asyncio.wait_for(pipe.read, TIMEOUT)
            except ValueError:
                failed = True
            assert failed
        if pipe is self.encryptor:
            self.restart_encryptor()
        else:
            self.restart_decryptor()

    async def run(self) -> None:
        actions = [self.set_key, self.add_key, self.remove_key, self.encrypt, self.decrypt_sent, self.decrypt]
        actions += [self.burst, self.end]
        try:
            for _ in range(self.inp.small(24)):
                if self.inp.exhausted():
                    break
                with contextlib.suppress(*EXPECTED):
                    await self.inp.choice(actions)()
        finally:
            self.encryptor.close()
            self.decryptor.close()


async def session(inp: Input) -> None:
    # the streams are made on the running loop
    await Session(inp).run()


def test_one_input(data: bytes) -> None:
    loop.run_until_complete(session(Input(data)))
    if len(failures) > 0:
        raise failures.pop()


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
