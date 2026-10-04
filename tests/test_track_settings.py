#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Settings, capabilities, constraints and content hints of tracks."""

from __future__ import annotations

import asyncio

import pytest
from typing_extensions import TypedDict

import webrtc
from tests.helpers import capture_mode, connect_track, run_isolated, wait_until

C = webrtc.MediaTrackConstraints


class VideoConstraints(TypedDict, total=False, closed=True):
    """Constraints taken by both MediaTrackConstraints and get_user_media."""

    width: int | webrtc.ConstrainULongRange
    frame_rate: float | webrtc.ConstrainDoubleRange


@pytest.mark.asyncio
async def test_camera_settings_and_capabilities() -> None:
    """A camera track has the size and measured frame rate of its frames, and the capabilities of the camera."""
    stream = await webrtc.media_devices.get_user_media(
        webrtc.MediaStreamConstraints(video=webrtc.MediaTrackConstraints(width=320, height=240, frame_rate=30))
    )
    track = stream.get_tracks()[0]

    await wait_until(lambda: track.get_settings().frame_rate is not None, 'the frame rate')
    settings = track.get_settings()
    assert (settings.width, settings.height, settings.aspect_ratio) == (320, 240, 320 / 240)
    assert settings.frame_rate is not None
    assert abs(settings.frame_rate - 30) < 5
    assert settings.device_id == 'synthetic-camera'
    assert settings.resize_mode == 'none'

    capabilities = track.get_capabilities()
    assert capabilities.width == webrtc.ULongRange(1, 4096)
    assert capabilities.frame_rate is not None
    assert capabilities.frame_rate.max is not None
    assert capabilities.frame_rate.max >= 60
    assert track.get_constraints() == webrtc.MediaTrackConstraints(width=320, height=240, frame_rate=30)
    track.stop()


@pytest.mark.asyncio
async def test_microphone_settings(audio_stream: webrtc.MediaStream) -> None:
    """A microphone track has the format of its samples, and no constraints."""
    track = audio_stream.get_tracks()[0]
    await wait_until(lambda: track.get_settings().sample_rate is not None, 'the audio format')
    settings = track.get_settings()
    assert (settings.sample_rate, settings.channel_count, settings.sample_size) == (48000, 1, 16)
    assert settings.echo_cancellation is False
    assert settings.device_id == 'synthetic-microphone'
    assert track.get_capabilities().sample_rate == webrtc.ULongRange(48000, 48000)
    assert track.get_constraints() == webrtc.MediaTrackConstraints()


@pytest.mark.asyncio
async def test_apply_constraints_to_the_camera(video_stream: webrtc.MediaStream) -> None:
    """Constraints change the size and frame rate of the camera, and are kept by the track."""
    track = video_stream.get_tracks()[0]
    await track.apply_constraints(
        C(width=160, height=webrtc.ConstrainULongRange(exact=120), frame_rate=webrtc.ConstrainDoubleRange(max=10))
    )
    await wait_until(lambda: track.get_settings().width == 160, 'the new size')

    def slowed() -> bool:
        frame_rate = track.get_settings().frame_rate
        return frame_rate is None or frame_rate < 12

    await wait_until(slowed, 'the new frame rate')
    assert track.get_settings().height == 120
    assert track.getConstraints().height == webrtc.ConstrainULongRange(exact=120)

    clone = track.clone()
    assert clone.get_settings().device_id == 'synthetic-camera'
    clone.stop()


@pytest.mark.asyncio
async def test_overconstrained(video_stream: webrtc.MediaStream, audio_stream: webrtc.MediaStream) -> None:
    """A required constraint the source can't satisfy fails, leaving the track as it was."""
    video = video_stream.get_tracks()[0]
    await video.apply_constraints(C(width=320))
    with pytest.raises(webrtc.OverconstrainedError) as error:
        await video.apply_constraints(C(width=webrtc.ConstrainULongRange(min=100000)))
    assert error.value.constraint == 'width'
    assert video.get_constraints().width == 320

    audio = audio_stream.get_tracks()[0]
    with pytest.raises(webrtc.OverconstrainedError):
        await audio.apply_constraints(C(sample_rate=webrtc.ConstrainULongRange(exact=44100)))
    await audio.apply_constraints(C(width=webrtc.ConstrainULongRange(exact=640)))
    # ideal values are satisfied as far as possible
    await audio.apply_constraints(C(sample_rate=44100, echo_cancellation=True))


@pytest.mark.asyncio
async def test_remote_track_settings(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, video_stream: webrtc.MediaStream
) -> None:
    """A remote track has the settings of what arrives, and no capabilities."""
    remote = await connect_track(caller, callee, video_stream.get_tracks()[0])
    await wait_until(lambda: remote.get_settings().width is not None, 'frames')
    settings = remote.get_settings()
    assert (settings.width, settings.height) == (640, 480)
    assert settings.device_id is None
    assert remote.get_capabilities() == webrtc.MediaTrackCapabilities()
    with pytest.raises(webrtc.OverconstrainedError):
        await remote.apply_constraints(C(width=webrtc.ConstrainULongRange(exact=100)))


def test_content_hint(audio_stream: webrtc.MediaStream, video_stream: webrtc.MediaStream) -> None:
    """Hints of the kind of the track are kept, others are ignored."""
    video, audio = video_stream.get_tracks()[0], audio_stream.get_tracks()[0]
    assert video.content_hint == ''
    assert audio.contentHint == ''
    video.content_hint = 'text'
    audio.content_hint = 'music'
    video.content_hint = 'speech'
    audio.content_hint = 'detail'
    assert (video.content_hint, audio.content_hint) == ('text', 'music')
    video.content_hint = ''
    assert video.content_hint == ''


@pytest.mark.asyncio
async def test_constraints_of_an_ended_track(video_stream: webrtc.MediaStream) -> None:
    """Constraints of an ended track are accepted, even ones it couldn't satisfy."""
    track = video_stream.get_tracks()[0]
    track.stop()
    await track.apply_constraints(C(width=webrtc.ConstrainULongRange(exact=100000)))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'constraints',
    [{'frame_rate': float('nan')}, {'frame_rate': float('inf')}, {'width': '1'}],
)
async def test_constraints_have_their_webidl_types(
    video_stream: webrtc.MediaStream, constraints: VideoConstraints
) -> None:
    """Unsigned longs and restricted doubles: other values are a TypeError."""
    with pytest.raises(TypeError):
        await video_stream.get_tracks()[0].apply_constraints(C(**constraints))
    with pytest.raises(TypeError):
        await webrtc.media_devices.get_user_media(
            webrtc.MediaStreamConstraints(video=webrtc.MediaTrackConstraints(**constraints))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('constraints', 'expected'),
    [
        ({'frame_rate': 10**9}, (640, 480, 120)),
        ({'frame_rate': 0}, (640, 480, 1)),
        ({'frame_rate': webrtc.ConstrainDoubleRange(ideal=-5)}, (640, 480, 1)),
    ],
)
async def test_camera_stays_within_its_capabilities(
    video_stream: webrtc.MediaStream, constraints: VideoConstraints, expected: tuple[int, int, float]
) -> None:
    """Ideal values beyond the capabilities select the nearest ones."""
    track = video_stream.get_tracks()[0]
    await track.apply_constraints(C(**constraints))
    assert capture_mode(track) == expected

    track = (
        await webrtc.media_devices.get_user_media(
            webrtc.MediaStreamConstraints(video=webrtc.MediaTrackConstraints(**constraints))
        )
    ).get_tracks()[0]
    assert capture_mode(track) == expected
    track.stop()


def test_get_user_media_rejects_what_the_camera_cannot_do() -> None:
    with pytest.raises(webrtc.OverconstrainedError):
        asyncio.run(
            webrtc.media_devices.get_user_media(
                webrtc.MediaStreamConstraints(
                    video=webrtc.MediaTrackConstraints(width=webrtc.ConstrainULongRange(exact=5000))
                )
            )
        )
    with pytest.raises(webrtc.OverconstrainedError):
        asyncio.run(
            webrtc.media_devices.get_user_media(
                webrtc.MediaStreamConstraints(
                    video=webrtc.MediaTrackConstraints(frame_rate=webrtc.ConstrainDoubleRange(min=500))
                )
            )
        )


def test_camera_of_impossible_sizes() -> None:
    """A camera of no size, a negative one or a huge one aborted the process."""
    output = run_isolated(
        """
        import asyncio
        import webrtc

        async def main():
            constraints = webrtc.MediaStreamConstraints(video=True)
            track = (await webrtc.media_devices.get_user_media(constraints)).get_tracks()[0]
            C, Range = webrtc.MediaTrackConstraints, webrtc.ConstrainULongRange
            for negative in (C(width=-1), C(height=Range(ideal=-5))):
                await track.apply_constraints(negative)
                print(track._native_obj._camera())
            await track.apply_constraints(C(width=10**6, height=Range(ideal=10**6)))
            print(track._native_obj._camera())
            await track.apply_constraints(C(width=0, height=0))
            print(track._native_obj._camera())
            track.stop()
            constraints = webrtc.MediaStreamConstraints(video=webrtc.MediaTrackConstraints(width=0, height=0))
            (track,) = (await webrtc.media_devices.get_user_media(constraints)).get_tracks()
            print(track._native_obj._camera())

        asyncio.run(main())
        """
    )
    assert output.count('(4096, 4096, 30.0)') == 1, output
    assert output.count('(1, 480, 30.0)') == 1, output
    assert output.count('(1, 1, 30.0)') == 3, output


def test_constraints_from_json() -> None:
    """The JSON form of constraints has nested constraints of each type, which are converted too."""
    constraints = C.from_json({
        'width': {'exact': 320},
        'frameRate': {'ideal': 15, 'max': 30},
        'deviceId': ['a', 'b'],
        'resizeMode': {'exact': 'none'},
        'echoCancellation': {'ideal': 'all'},
        'autoGainControl': {'exact': False},
        'height': 240,
        'advanced': [{'width': {'min': 100}}, {'aspectRatio': 1.5}],
        'unknown': 1,
    })
    assert constraints == C(
        width=webrtc.ConstrainULongRange(exact=320),
        frame_rate=webrtc.ConstrainDoubleRange(max=30, ideal=15),
        device_id=['a', 'b'],
        resize_mode=webrtc.ConstrainDOMStringParameters(exact='none'),
        echo_cancellation=webrtc.ConstrainBooleanOrDOMStringParameters(ideal='all'),
        auto_gain_control=webrtc.ConstrainBooleanParameters(exact=False),
        height=240,
        advanced=[
            webrtc.MediaTrackConstraintSet(width=webrtc.ConstrainULongRange(min=100)),
            webrtc.MediaTrackConstraintSet(aspect_ratio=1.5),
        ],
    )
