#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The sender that encodes and sends the media of a track."""

from __future__ import annotations

from typing import TYPE_CHECKING

import webrtc
from webrtc import (
    InvalidModificationError,
    InvalidRangeError,
    InvalidStateError,
    MediaType,
    RTCRtpCapabilities,
    RTCRtpSendParameters,
    RTCStatsReport,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.native_calls import call_native
from webrtc.utils.operations import later
from webrtc.utils.task_queue import TaskQueue

if TYPE_CHECKING:
    from collections.abc import Sequence


class RTCRtpSender(WebRTCObject[wrtc.RTCRtpSender]):
    """Encodes the media of a track and sends it to the remote peer, and controls how it's sent.

    Each :obj:`webrtc.RTCRtpTransceiver` of an :obj:`webrtc.RTCPeerConnection` has one.

    See :mdn:`RTCRtpSender`.
    """

    _class = wrtc.RTCRtpSender

    @property
    def track(self) -> webrtc.MediaStreamTrack | None:
        """:obj:`webrtc.MediaStreamTrack`, optional: The track being sent, or :obj:`None` if nothing is.

        Change it with :meth:`replace_track`.

        See :mdn:`RTCRtpSender/track`.
        """
        return webrtc.MediaStreamTrack._wrap_optional(self._native_obj.track)

    @property
    def transport(self) -> webrtc.RTCDtlsTransport | None:
        """:obj:`webrtc.RTCDtlsTransport`, optional: The transport the packets go over.

        It's :obj:`None` until there's one.
        See :mdn:`RTCRtpSender/transport`.
        """
        return webrtc.RTCDtlsTransport._wrap_optional(self._native_obj.transport)

    @property
    def dtmf(self) -> webrtc.RTCDTMFSender | None:
        """:obj:`webrtc.RTCDTMFSender`, optional: Sends DTMF tones, or is :obj:`None` for a video sender.

        See :mdn:`RTCRtpSender/dtmf`.
        """
        return webrtc.RTCDTMFSender._wrap_optional(self._native_obj.dtmf)

    @property
    def transform(self) -> webrtc.RTCRtpScriptTransform | webrtc.RTCRtpSFrameEncryptor | None:
        """:obj:`webrtc.RTCRtpScriptTransform` or :obj:`webrtc.RTCRtpSFrameEncryptor`, optional: The frame transform.

        It changes the encoded frames before they're sent. With :obj:`None`, frames are sent as encoded.
        A transform serves one sender or receiver for its lifetime, so once attached it can't be set elsewhere.

        See :mdn:`RTCRtpSender/transform`.

        Raises:
            TypeError: If the value set isn't a transform of a sender.
            webrtc.InvalidStateError: If the transform set had a sender or receiver.
        """
        native = self._native_obj.transform
        if isinstance(native, wrtc.SFrameTransform):
            return webrtc.RTCRtpSFrameEncryptor._wrap(native)
        return webrtc.RTCRtpScriptTransform._of_native(native)

    @transform.setter
    def transform(self, transform: webrtc.RTCRtpScriptTransform | webrtc.RTCRtpSFrameEncryptor | None) -> None:
        self._native_obj.transform = _native_transform(transform, webrtc.RTCRtpSFrameEncryptor)

    @property
    def _kind(self) -> webrtc.MediaType:
        # the kind of the native object, which the receiver's track has too
        return self._native_obj.kind

    def get_parameters(self) -> webrtc.RTCRtpSendParameters:
        """Returns the parameters the sender sends with.

        To change them, modify the result and pass it to :meth:`set_parameters` before the current task of the
        event loop ends. Parameters from an earlier task are rejected. Video encodings without
        ``scale_resolution_down_by`` get the effective value filled in.

        See :mdn:`RTCRtpSender/getParameters`.

        Returns:
            :obj:`webrtc.RTCRtpSendParameters`: The parameters, with a new ``transaction_id``.
        """
        parameters = RTCRtpSendParameters._from_native(self._native_obj.getParameters())
        if self._kind == MediaType.video:
            _default_scale_resolution_down_by(parameters.encodings)
        # they expire when the current task (with the code it resumed) is over, never without a loop
        _ = TaskQueue.post_to_running(self._native_obj._expireParameters, parameters.transaction_id, after_ready=True)
        return parameters

    async def set_parameters(
        self,
        parameters: webrtc.RTCRtpSendParameters,
        set_parameter_options: webrtc.RTCSetParameterOptions | None = None,
    ) -> None:
        """Changes the encodings and the degradation preference the sender sends with.

        See :mdn:`RTCRtpSender/setParameters`.

        Args:
            parameters (:obj:`webrtc.RTCRtpSendParameters`): The parameters :meth:`get_parameters` returned in the
                current task, with the changes made.
            set_parameter_options (:obj:`webrtc.RTCSetParameterOptions`, optional): How to change the encodings,
                like sending a key frame right away.

        Raises:
            webrtc.InvalidStateError: If :meth:`get_parameters` wasn't called in the current task, or the
                transceiver of the sender is stopped.
            webrtc.InvalidModificationError: If the ``transaction_id``, the codecs, the header extensions,
                the RTCP parameters, the number of encodings or their ``rid`` changed, the codec of an encoding
                isn't negotiated, or ``encoding_options`` isn't empty or one per encoding.
            webrtc.InvalidRangeError: If a value is out of range, like ``scale_resolution_down_by`` below 1.
            TypeError: If ``max_bitrate`` isn't an unsigned 32-bit integer, or a video value isn't a finite number.
        """
        if self._native_obj._transceiverStopped():
            msg = 'The transceiver of the sender is stopped'
            raise InvalidStateError(msg)
        last = self._native_obj._lastParameters()
        if last is None:
            msg = 'get_parameters() must be called before set_parameters(), in the same task'
            raise InvalidStateError(msg)
        options = set_parameter_options.encoding_options if set_parameter_options is not None else None
        _check_unchanged(parameters, RTCRtpSendParameters._from_native(last), options)
        if self._kind == MediaType.video:
            _check_video_ranges(parameters.encodings)

        kind = self._kind
        # a copy (pybind returns one): changed, then set back
        encodings = last.encodings
        for native, encoding in zip(encodings, parameters.encodings):
            _ = encoding._for_kind(kind)._apply(native)
        for native, option in zip(encodings, options if options is not None else ()):
            native.requestKeyFrame = bool(option.key_frame)
        last.encodings = encodings
        last.degradationPreference = parameters.degradation_preference
        await call_native(self._native_obj.setParameters, last)

    async def replace_track(self, with_track: webrtc.MediaStreamTrack | None) -> None:
        """Replaces the track the sender sends, without renegotiating.

        It runs in the operations chain of the connection, after the operations queued before it (like setting a
        description), and never before the calling code continues.

        See :mdn:`RTCRtpSender/replaceTrack`.

        Args:
            with_track (:obj:`webrtc.MediaStreamTrack`, optional): The new track of the same kind, or :obj:`None`
                to stop sending.

        Raises:
            TypeError: If the track is of another kind.
            webrtc.InvalidStateError: If the transceiver of the sender is stopped, or the connection is closed.
        """
        if with_track is not None and with_track.kind != self._kind:
            msg = f'a {with_track.kind} track can not replace the track of a {self._kind} sender'
            raise TypeError(msg)

        def replace() -> None:
            native_track = with_track._native_obj if with_track is not None else None
            if self._native_obj._transceiverStopped() or not self._native_obj.replaceTrack(native_track):
                msg = 'The track of a stopped sender can not be replaced'
                raise InvalidStateError(msg)

        connection = wrtc.RTCPeerConnection._connectionOf(self._native_obj)
        if connection is None:
            replace()
            return
        pc = webrtc.RTCPeerConnection._wrap(connection)
        async with pc._operation():
            pc._check_state('replace the track')
            await later()
            replace()

    def set_streams(self, *streams: webrtc.MediaStream) -> None:
        """Sets the streams the remote peer puts the track of the sender in, from the next negotiation.

        Repeated streams count once.

        See :mdn:`RTCRtpSender/setStreams`.

        Args:
            *streams (:obj:`webrtc.MediaStream`): The streams. Pass none to put the track in no stream.
        """
        ids: list[str] = []
        for stream in streams:
            if stream.id not in ids:
                ids.append(stream.id)
        self._native_obj.setStreams(ids)

    @staticmethod
    def get_capabilities(kind: webrtc.MediaType | webrtc.MediaTypeValue) -> webrtc.RTCRtpCapabilities | None:
        """Returns the codecs and header extensions senders of a kind support.

        See :mdn:`RTCRtpSender/getCapabilities_static`.

        Args:
            kind (:obj:`webrtc.MediaType`): Audio or video.

        Returns:
            :obj:`webrtc.RTCRtpCapabilities`, optional: The capabilities, or :obj:`None` for another kind.
        """
        return RTCRtpCapabilities._supported(wrtc.RTCRtpSender, kind)

    async def get_stats(self) -> webrtc.RTCStatsReport:
        """Collects the stats of the sender and of the objects they refer to.

        See :mdn:`RTCRtpSender/getStats`.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
        """
        return RTCStatsReport._from_native(await call_native(self._native_obj.getStats))

    #: Alias for :attr:`get_stats`
    getStats = get_stats
    #: Alias for :attr:`get_parameters`
    getParameters = get_parameters
    #: Alias for :attr:`set_parameters`
    setParameters = set_parameters
    #: Alias for :attr:`replace_track`
    replaceTrack = replace_track
    #: Alias for :attr:`set_streams`
    setStreams = set_streams
    #: Alias for :attr:`get_capabilities`
    getCapabilities = get_capabilities


def _native_transform(
    transform: webrtc.RTCRtpScriptTransform | webrtc.RTCRtpSFrameEncryptor | webrtc.RTCRtpSFrameDecryptor | None,
    sframe: type[webrtc.RTCRtpSFrameEncryptor | webrtc.RTCRtpSFrameDecryptor],
) -> wrtc._RtpTransform | None:
    """The native transform of the transform attribute of a sender or receiver, whose SFrame transform is given."""
    if transform is None:
        return None
    if not isinstance(transform, (webrtc.RTCRtpScriptTransform, sframe)):
        msg = (
            f'transform must be an RTCRtpScriptTransform, an {sframe.__name__} or None, not {type(transform).__name__}'
        )
        raise TypeError(msg)
    return transform._native_obj


def _check_unchanged(
    parameters: webrtc.RTCRtpSendParameters,
    returned: webrtc.RTCRtpSendParameters,
    encoding_options: Sequence[webrtc.RTCEncodingOptions] | None,
) -> None:
    """Checks what set_parameters() can't change against the parameters get_parameters() returned last.

    Raises:
        webrtc.InvalidModificationError: If something changed, or ``encoding_options`` isn't empty or one per encoding.
    """
    if parameters.transaction_id != returned.transaction_id:
        msg = "The transaction_id doesn't match the one of the last get_parameters()"
        raise InvalidModificationError(msg)
    for name in ('codecs', 'header_extensions', 'rtcp'):
        if getattr(parameters, name) != getattr(returned, name):
            msg = f'{name} of the parameters can not be changed'
            raise InvalidModificationError(msg)
    if [e.rid for e in parameters.encodings] != [e.rid for e in returned.encodings]:
        msg = 'The number of encodings and their rid can not be changed'
        raise InvalidModificationError(msg)
    if encoding_options is not None and len(encoding_options) not in {0, len(parameters.encodings)}:
        msg = 'encoding_options must have one value per encoding'
        raise InvalidModificationError(msg)


def _check_video_ranges(encodings: list[webrtc.RTCRtpEncodingParameters]) -> None:
    """Checks the values of video encodings, before the native WebRTC engine gets them.

    Raises:
        webrtc.InvalidRangeError: If a value is out of range.
    """
    for encoding in encodings:
        if encoding.scale_resolution_down_by is not None and encoding.scale_resolution_down_by < 1:
            msg = 'scale_resolution_down_by must be at least 1'
            raise InvalidRangeError(msg)
        if encoding.max_framerate is not None and encoding.max_framerate < 0:
            msg = 'max_framerate must not be negative'
            raise InvalidRangeError(msg)


def _default_scale_resolution_down_by(encodings: list[webrtc.RTCRtpEncodingParameters]) -> None:
    """Video encodings without scale_resolution_down_by scale by 1, or by descending powers of 2 if none has one."""
    if all(e.scale_resolution_down_by is None for e in encodings):
        for i, encoding in enumerate(encodings):
            encoding.scale_resolution_down_by = float(2 ** (len(encodings) - 1 - i))
    for encoding in encodings:
        if encoding.scale_resolution_down_by is None:
            encoding.scale_resolution_down_by = 1.0
