#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes SFrame (RFC 9605) natively: headers, key derivation, and decryption of what a remote peer sends.

A decryptor parses untrusted frames: whatever the bytes, it gives the plaintext or nothing. Oracles check that a
header parses back to its key id and counter, and that every suite decrypts what it encrypted, and nothing tampered.
"""

from __future__ import annotations

import contextlib
import pathlib
import sys

import atheris

with atheris.instrument_imports():
    from inputs import Input

from webrtc import wrtc

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from tests.helpers import mistyped

# tag sizes (Nt) of the suite identifiers
TAGS = {1: 10, 2: 8, 3: 4, 4: 16, 5: 16, 6: 10, 7: 8, 8: 4}
SUITES = list(TAGS)
# pybind11 raises TypeError for arguments it can't convert, and for strided buffers; ValueError for unknown suites
EXPECTED = (TypeError, ValueError)
MAX_U64 = 2**64 - 1
NONE, AUTHENTICATION, KEY_ID, SYNTAX = 0, 1, 2, 3


def u64(inp: Input) -> int:
    if inp.flag():
        return inp.unsigned(16) & MAX_U64
    return inp.small(MAX_U64) >> (inp.small(8) * 8)


def field_size(value: int) -> int:
    return 0 if value < 8 else (value.bit_length() + 7) // 8


def suite(inp: Input) -> int:
    return inp.choice(SUITES) if inp.small(7) < 7 else mistyped(inp.integer(16))


def octets(inp: Input, limit: int = 64) -> bytes:
    return bytes(inp.contiguous(inp.small(limit)))


def parse(inp: Input) -> None:
    """Any bytes: a header within them, which parses the same from its own bytes and not without its last one."""
    data = inp.contiguous(inp.small(40))
    header = wrtc._sframeParseHeader(data)
    if header is None:
        return
    key_id, counter, size = header
    raw = bytes(data)
    assert 1 <= size <= min(len(raw), 17)
    assert 0 <= key_id <= MAX_U64
    assert 0 <= counter <= MAX_U64
    assert wrtc._sframeParseHeader(raw[:size]) == header
    assert wrtc._sframeParseHeader(raw[: size - 1]) is None


def header(inp: Input) -> None:
    key_id, counter = u64(inp), u64(inp)
    encoded = wrtc._sframeHeader(key_id, counter)
    size = 1 + field_size(key_id) + field_size(counter)
    assert len(encoded) == size
    assert wrtc._sframeParseHeader(encoded + octets(inp, 8)) == (key_id, counter, size)


def decrypt(inp: Input) -> None:
    """Arbitrary ciphertexts, or tampered real ones: decrypted or None, never a crash."""
    ciphertext = inp.contiguous(inp.small(256))
    if inp.flag():
        real = wrtc._sframeEncrypt(inp.choice(SUITES), octets(inp), u64(inp), u64(inp), b'', octets(inp, 128))
        tampered = bytearray(real)
        for _ in range(inp.small(4)):
            if len(tampered) > 0:
                tampered[inp.small(len(tampered) - 1)] ^= inp.small(254) + 1
        ciphertext = bytes(tampered[: inp.small(len(tampered))] if inp.flag() else tampered)
    out = wrtc._sframeDecrypt(suite(inp), inp.contiguous(inp.small(64)), inp.contiguous(inp.small(32)), ciphertext)
    assert out is None or isinstance(out, bytes)


def round_trip(inp: Input) -> None:
    """Encrypted then decrypted gives the plaintext back; any byte changed, or other metadata, gives None."""
    suite_id = inp.choice(SUITES)
    key, key_id, counter = octets(inp), u64(inp), u64(inp)
    metadata, plaintext = octets(inp, 32), octets(inp, 512)
    ciphertext = wrtc._sframeEncrypt(suite_id, key, key_id, counter, metadata, plaintext)
    size = 1 + field_size(key_id) + field_size(counter)
    assert len(ciphertext) == size + len(plaintext) + TAGS[suite_id]
    assert wrtc._sframeParseHeader(ciphertext) == (key_id, counter, size)
    assert wrtc._sframeDecrypt(suite_id, key, metadata, ciphertext) == plaintext
    assert wrtc._sframeEncrypt(suite_id, key, key_id, counter, metadata, plaintext) == ciphertext

    tampered = bytearray(ciphertext)
    tampered[inp.small(len(tampered) - 1)] ^= inp.small(254) + 1
    assert wrtc._sframeDecrypt(suite_id, key, metadata, tampered) is None
    other = octets(inp, 32)
    if other != metadata:
        assert wrtc._sframeDecrypt(suite_id, key, other, ciphertext) is None
    other = octets(inp)
    if other != key:
        assert wrtc._sframeDecrypt(suite_id, other, metadata, ciphertext) is None
    assert wrtc._sframeDecrypt(suite_id, key, metadata, ciphertext[: inp.small(size + TAGS[suite_id] - 1)]) is None


def derive(inp: Input) -> None:
    suite_id = suite(inp)
    key, salt = wrtc._sframeDerive(
        suite_id, inp.contiguous(inp.small(128)), u64(inp) if inp.small(7) < 7 else mistyped(inp.integer(16))
    )
    assert len(salt) == 12
    assert len(key) in {16, 32, 48, 96}


class Context:
    """The native transform of the streams: keys added, removed and replaced between decryptions."""

    def __init__(self, inp: Input) -> None:
        self.inp = inp
        self.suite = inp.choice(SUITES)
        self.decryptor_suite = self.suite if inp.small(7) < 7 else inp.choice(SUITES)
        self.encryptor = wrtc.SFrameTransform(self.suite, encrypting=True)
        self.decryptor = wrtc.SFrameTransform(self.decryptor_suite, encrypting=False)
        self.keys: dict[int, bytes] = {}
        self.sending: tuple[bytes, int] | None = None

    def key_id(self) -> int:
        return u64(self.inp) if self.inp.small(3) < 3 else self.inp.choice([0, *self.keys])

    def add_key(self) -> None:
        key, key_id = octets(self.inp), self.key_id()
        assert self.decryptor.addDecryptionKey(key, key_id)
        self.keys[key_id] = key

    def remove_key(self) -> None:
        key_id = self.key_id()
        self.decryptor.removeDecryptionKey(key_id)
        self.keys.pop(key_id, None)

    def set_key(self) -> None:
        key, key_id = octets(self.inp), self.key_id()
        assert self.encryptor.setEncryptionKey(key, key_id)
        self.sending = (key, key_id)
        if self.inp.flag():
            assert self.decryptor.addDecryptionKey(key, key_id)
            self.keys[key_id] = key

    def round_trip(self) -> None:
        plaintext = self.inp.contiguous(self.inp.small(256))
        ciphertext = self.encryptor.encrypt(plaintext)
        assert (ciphertext is None) == (self.sending is None)
        if ciphertext is None or self.sending is None:
            return
        key, key_id = self.sending
        result = self.decryptor.decrypt(ciphertext)
        if key_id not in self.keys:
            assert result == (None, KEY_ID, key_id)
        elif self.suite == self.decryptor_suite and self.keys[key_id] == key:
            assert result == (bytes(plaintext), NONE, None)
        else:
            assert result[0] is None
            assert result[1] in {AUTHENTICATION, SYNTAX}

    def decrypt(self) -> None:
        out, error, key_id = self.decryptor.decrypt(self.inp.contiguous(self.inp.small(256)))
        assert error in {NONE, AUTHENTICATION, KEY_ID, SYNTAX}
        assert (out is None) == (error != NONE)
        assert (key_id is not None) == (error == KEY_ID)
        assert key_id is None or key_id not in self.keys

    def run(self) -> None:
        actions = [self.add_key, self.remove_key, self.set_key, self.round_trip, self.decrypt]
        for _ in range(self.inp.small(12)):
            if self.inp.exhausted():
                break
            self.inp.choice(actions)()


def context(inp: Input) -> None:
    Context(inp).run()


def test_one_input(data: bytes) -> None:
    inp = Input(data)
    with contextlib.suppress(*EXPECTED):
        inp.choice([parse, header, decrypt, round_trip, derive, context])(inp)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
