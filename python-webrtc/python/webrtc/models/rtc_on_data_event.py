#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import AnyStr

from webrtc import wrtc, WebRTCObject


# TODO rename to RTCAudioData
class RTCOnDataEvent(WebRTCObject):
    """Audio data samples representation.

    Note:
        :obj:`webrtc.RTCOnDataEvent` should represent 10 ms of audio samples.
    """

    _class = wrtc.RTCOnDataEvent

    def __init__(self, audio_data: AnyStr, number_of_frames: int):
        self._set_native_obj(self._class(audio_data, number_of_frames))

    @property
    def audio_data(self) -> AnyStr:
        # TODO actually its number. could be represented as string in python
        """:obj:`AnyStr`: An audio data."""
        return self._native_obj.audioData

    @audio_data.setter
    def audio_data(self, value: AnyStr):
        self._native_obj.audioData = value

    @property
    def number_of_frames(self) -> int:
        """:obj:`int`: A number of frames."""
        return self._native_obj.numberOfFrames

    @number_of_frames.setter
    def number_of_frames(self, value: int):
        self._native_obj.numberOfFrames = value

    @property
    def sample_rate(self) -> int:
        """:obj:`int`: A sample rate."""
        return self._native_obj.sampleRate

    @sample_rate.setter
    def sample_rate(self, value: int):
        self._native_obj.sampleRate = value

    @property
    def bits_per_sample(self) -> int:
        """:obj:`int`: Bits per sample."""
        return self._native_obj.bitsPerSample

    @bits_per_sample.setter
    def bits_per_sample(self, value: int):
        self._native_obj.bitsPerSample = value

    @property
    def channel_count(self) -> int:
        """:obj:`int`: A channel count."""
        return self._native_obj.channelCount

    @channel_count.setter
    def channel_count(self, value: int):
        self._native_obj.channelCount = value

    #: Alias for :attr:`audio_data`
    audioData = audio_data
    #: Alias for :attr:`number_of_frames`
    numberOfFrames = number_of_frames
    #: Alias for :attr:`sample_rate`
    sampleRate = sample_rate
    #: Alias for :attr:`bits_per_sample`
    bitsPerSample = bits_per_sample
    #: Alias for :attr:`channel_count`
    channelCount = channel_count
