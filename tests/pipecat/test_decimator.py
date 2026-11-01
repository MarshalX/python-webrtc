#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The microphone's decimator, on tones and clicks, without a connection."""

from __future__ import annotations

import math

import numpy as np
import pytest

from webrtc.pipecat._media import Decimator, _low_pass  # ruff: ignore[import-private-name]

TRACK_RATE = 48000
#: what the reader decimates at once
FRAME = TRACK_RATE // 50
RATES = [8000, 16000, 24000]
AMPLITUDE = 16000


def tone(frequency: float, seconds: float = 1) -> np.ndarray:
    times = np.arange(round(seconds * TRACK_RATE)) / TRACK_RATE
    return (AMPLITUDE * np.sin(2 * np.pi * frequency * times)).astype(np.int16)


def in_frames(decimator: Decimator, samples: np.ndarray) -> np.ndarray:
    return np.concatenate([decimator.decimate(samples[i : i + FRAME]) for i in range(0, len(samples), FRAME)])


def level_db(samples: np.ndarray) -> float:
    """The RMS level against the tones'."""
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    return 20 * math.log10(max(rms, 1e-9) / (AMPLITUDE / math.sqrt(2)))


def settled(samples: np.ndarray, rate: int) -> np.ndarray:
    """The output past the filter's start."""
    return samples[rate // 10 :]


@pytest.mark.parametrize('rate', RATES)
def test_a_frame_gives_20_ms(rate: int) -> None:
    decimator = Decimator(TRACK_RATE // rate)

    counts = {len(decimator.decimate(tone(440, 0.02))) for _ in range(20)}

    assert counts == {rate // 50}


@pytest.mark.parametrize('rate', RATES)
def test_chunks_of_any_size_decimate_as_one_stream(rate: int) -> None:
    audio = tone(440, 0.5)
    sizes = np.random.default_rng(1).integers(1, 1500, 100)
    bounds = [0, *np.cumsum(sizes)[np.cumsum(sizes) < len(audio)], len(audio)]

    whole = Decimator(TRACK_RATE // rate).decimate(audio)
    decimator = Decimator(TRACK_RATE // rate)
    chunked = np.concatenate([decimator.decimate(audio[start:end]) for start, end in zip(bounds, bounds[1:])])

    assert np.array_equal(whole, chunked)


@pytest.mark.parametrize('rate', RATES)
def test_the_band_stays_flat(rate: int) -> None:
    nyquist = rate / 2
    for frequency in (100, 1000, 0.5 * nyquist, 0.9 * nyquist):
        out = in_frames(Decimator(TRACK_RATE // rate), tone(frequency))

        assert abs(level_db(settled(out, rate))) < 0.5


@pytest.mark.parametrize('rate', RATES)
def test_what_would_fold_into_the_band_is_60_db_down(rate: int) -> None:
    nyquist = rate / 2
    # from the rate less the band's end, a tone folds back into the band, up to the track's Nyquist frequency
    for frequency in np.linspace(1.1 * nyquist, TRACK_RATE / 2 - 100, 12):
        out = in_frames(Decimator(TRACK_RATE // rate), tone(frequency))

        assert level_db(settled(out, rate)) < -60


@pytest.mark.parametrize('rate', RATES)
def test_the_taps_keep_the_band_and_stop_what_would_fold_into_it(rate: int) -> None:
    factor = TRACK_RATE // rate
    response = np.abs(np.fft.rfft(_low_pass(factor).astype(np.float64), 1 << 16))
    # each bin's frequency as a share of the output's Nyquist frequency
    frequency = np.linspace(0, factor, len(response))
    gain_db = 20 * np.log10(np.maximum(response, 1e-12))

    assert np.abs(gain_db[frequency <= 0.9]).max() < 0.5
    assert gain_db[frequency >= 1.1].max() < -60


@pytest.mark.parametrize('rate', RATES)
def test_the_filter_has_linear_phase_and_delays_3_ms_at_most(rate: int) -> None:
    decimator = Decimator(TRACK_RATE // rate)
    factor, blocks = decimator._phases.shape
    taps = decimator._phases.T.reshape(-1)[blocks * factor - (2 * decimator.delay_samples + 1) :]

    assert np.array_equal(taps, taps[::-1])
    assert decimator.delay_samples / TRACK_RATE <= 0.003


def test_a_click_comes_out_after_the_filter_delay() -> None:
    decimator = Decimator(3)
    click = np.zeros(TRACK_RATE // 10, np.int16)
    click[TRACK_RATE // 20] = 32767

    out = in_frames(decimator, click)

    # an output sample comes every third input sample, so the peak is the one nearest the click and the delay
    peak = int(np.argmax(np.abs(out)))
    assert abs(peak * 3 - (TRACK_RATE // 20 + decimator.delay_samples)) <= 1
