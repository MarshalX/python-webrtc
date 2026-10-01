#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Hostile media input: buffers, sizes and formats that must be rejected rather than read, written or sent."""

from __future__ import annotations

from typing import Callable

import pytest

import webrtc
import wrtc
from tests.helpers import run_isolated

WIDTH, HEIGHT = 16, 16
I420_SIZE = WIDTH * HEIGHT * 3 // 2


def i420_frame() -> webrtc.VideoFrame:
    return webrtc.VideoFrame(
        bytes(I420_SIZE),
        webrtc.VideoFrameBufferInit(format='I420', coded_width=WIDTH, coded_height=HEIGHT, timestamp=0),
    )


def reversed_view(size: int) -> memoryview:
    """A view of size bytes whose pointer is its last byte: read or written forward, it's out of its buffer."""
    return memoryview(bytearray(size))[::-1]


def strided_view(size: int) -> memoryview:
    return memoryview(bytearray(size * 2))[::2]


@pytest.mark.parametrize('view', [reversed_view, strided_view])
def test_frame_from_non_contiguous_buffer_is_rejected(view: Callable[[int], memoryview]) -> None:
    with pytest.raises(TypeError, match='contiguous'):
        webrtc.VideoFrame(
            view(I420_SIZE),
            webrtc.VideoFrameBufferInit(format='I420', coded_width=WIDTH, coded_height=HEIGHT, timestamp=0),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('view', [reversed_view, strided_view])
@pytest.mark.parametrize('options', [None, webrtc.VideoFrameCopyToOptions(format='RGBA')])
async def test_frame_copy_to_non_contiguous_destination_is_rejected(
    view: Callable[[int], memoryview], options: webrtc.VideoFrameCopyToOptions | None
) -> None:
    frame = i420_frame()
    with pytest.raises(TypeError, match='contiguous'):
        await frame.copy_to(view(frame.allocation_size(options)), options)
    frame.close()


@pytest.mark.parametrize('view', [reversed_view, strided_view])
def test_audio_copy_to_non_contiguous_destination_is_rejected(view: Callable[[int], memoryview]) -> None:
    data = webrtc.AudioData(
        webrtc.AudioDataInit(
            format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=2, timestamp=0, data=bytes(1920)
        )
    )
    with pytest.raises(TypeError, match='contiguous'):
        data.copy_to(view(1920), webrtc.AudioDataCopyToOptions(plane_index=0))
    data.close()


def test_native_bounds_checks_do_not_overflow() -> None:
    """Offsets and strides near the top of size_t wrap around in naive bounds checks."""
    top = 2**64 - 1
    planes = [(0, WIDTH), (WIDTH * HEIGHT, WIDTH // 2), (WIDTH * HEIGHT * 5 // 4, WIDTH // 2)]
    with pytest.raises(ValueError, match="layout doesn't fit"):
        wrtc.VideoFrameBuffer.fromData('I420', WIDTH, HEIGHT, bytes(I420_SIZE), [(top, WIDTH), *planes[1:]])
    with pytest.raises(ValueError, match="layout doesn't fit"):
        wrtc.VideoFrameBuffer.fromData('I420', WIDTH, HEIGHT, bytes(I420_SIZE), [(0, 2**63)] * 3)
    with pytest.raises(ValueError, match='positive size'):
        wrtc.VideoFrameBuffer.fromData('I420', 2**31 - 1, 2**31 - 1, bytes(I420_SIZE), [(0, 2**31 - 1)] * 3)

    buffer = wrtc.VideoFrameBuffer.fromData('I420', WIDTH, HEIGHT, bytes(I420_SIZE), planes)
    destination = bytearray(I420_SIZE)
    half = (0, 0, WIDTH // 2, HEIGHT // 2, 0, WIDTH // 2)
    with pytest.raises(ValueError, match='out of the bounds of the frame'):
        buffer.copyPlanes(destination, [(0, 0, WIDTH, HEIGHT, top - 100, 1), half, half])
    with pytest.raises(ValueError, match='out of the bounds of the frame'):
        buffer.copyPlanes(destination, [(0, top, WIDTH, 2, 0, WIDTH), half, half])
    with pytest.raises(ValueError, match='destination is too small'):
        buffer.convertTo(bytearray(16), 'RGBA', 0, 0, WIDTH, HEIGHT, top - 100, WIDTH * 4, '', fullRange=False)
    with pytest.raises(ValueError, match='rect is out of the bounds'):
        buffer.convertTo(bytearray(WIDTH * HEIGHT * 4), 'RGBA', 2**31 - 1, 0, 2, 1, 0, WIDTH * 4, '', fullRange=False)

    with pytest.raises(ValueError, match='out of the bounds of the samples'):
        wrtc.copyAudioSamples(bytes(16), 's16', 2**40, 2**40, bytearray(16), 's16', 0, 0, 1)
    with pytest.raises(ValueError, match='out of the bounds of the samples'):
        wrtc.copyAudioSamples(bytes(16), 's16', 1, 4, bytearray(16), 's16', 0, top, 2)
    with pytest.raises(ValueError, match='out of the bounds of the samples'):
        wrtc.copyAudioSamples(bytes(16), 's16', 0, 4, bytearray(16), 's16-planar', 0, 0, 1)


@pytest.mark.parametrize('rate', [float('inf'), float('nan'), 0, -1])
def test_audio_data_sample_rate_is_positive_and_finite(rate: float) -> None:
    with pytest.raises(TypeError):
        webrtc.AudioData(
            webrtc.AudioDataInit(
                format='s16', sample_rate=rate, number_of_frames=1, number_of_channels=1, timestamp=0, data=bytes(2)
            )
        )


def test_generator_rejects_audio_libwebrtc_cannot_send() -> None:
    """Audio beyond libwebrtc's frames or resampler is rejected, it aborted the process."""
    output = run_isolated(
        """
        import asyncio
        import webrtc
        from tests.helpers import connect

        async def write(rate, channels):
            generator = webrtc.MediaStreamTrackGenerator('audio')
            caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
            caller.add_track(generator)
            await connect(caller, callee)
            writer = generator.writable.get_writer()
            # 10 ms, a few at most: the rate alone is rejected, a 2**40 Hz buffer would be 22 GB
            frames = max(1, min(int(rate) // 100, 4800))
            try:
                for i in range(10):
                    data = webrtc.AudioData(webrtc.AudioDataInit(
                        format='s16', sample_rate=rate, number_of_frames=frames, number_of_channels=channels,
                        timestamp=i * 10000, data=bytes(frames * channels * 2)))
                    await writer.write(data)
                    await asyncio.sleep(0.01)
                result = 'written'
            except webrtc.NotSupportedError:
                result = 'rejected'
            caller.close()
            callee.close()
            return result

        async def main():
            for rate, channels in ((1000, 1), (150, 1), (0.5, 1), (2**40, 1), (1000000, 1), (48000, 24),
                                   (384000, 16)):
                print(rate, channels, await write(rate, channels))
            for rate, channels in ((8000, 1), (48000, 16), (384000, 2), (44100, 2)):
                print(rate, channels, await write(rate, channels))

        asyncio.run(main())
        """
    )
    results = [line.split()[-1] for line in output.splitlines() if line.endswith(('written', 'rejected'))]
    assert results == ['rejected'] * 7 + ['written'] * 4, output
