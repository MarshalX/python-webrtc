#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, List, Optional, Sequence

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
    import webrtc


class RTCRtpSender(WebRTCObject):
    """The :obj:`webrtc.RTCRtpSender` interface sends the media of a track, encoded, to the remote peer, and
    controls how it's sent. It's the sender of an :obj:`webrtc.RTCRtpTransceiver` of an
    :obj:`webrtc.RTCPeerConnection`.
    """

    _class = wrtc.RTCRtpSender

    def _check_parameters(
        self,
        parameters: 'webrtc.RTCRtpSendParameters',
        last: 'wrtc.RtpParameters',
        key_frames: Optional[Sequence[bool]],
    ) -> None:
        """Checks the parameters set_parameters() takes against the ones get_parameters() returned last, as the
        specification requires, before libwebrtc gets them."""
        returned = RTCRtpSendParameters._from_native(last)
        if parameters.transaction_id != returned.transaction_id:
            raise InvalidModificationError("The transaction_id doesn't match the one of the last get_parameters()")
        for name in ('codecs', 'header_extensions', 'rtcp'):
            if getattr(parameters, name) != getattr(returned, name):
                raise InvalidModificationError(f'{name} of the parameters can not be changed')
        if [e.rid for e in parameters.encodings] != [e.rid for e in returned.encodings]:
            raise InvalidModificationError('The number of encodings and their rid can not be changed')
        if key_frames is not None and len(key_frames) != len(parameters.encodings):
            raise InvalidModificationError('key_frames must have one value per encoding')
        if self.kind != MediaType.video:
            return
        for encoding in parameters.encodings:
            if encoding.scale_resolution_down_by is not None and encoding.scale_resolution_down_by < 1:
                raise InvalidRangeError('scale_resolution_down_by must be at least 1')
            if encoding.max_framerate is not None and encoding.max_framerate < 0:
                raise InvalidRangeError('max_framerate must not be negative')

    @property
    def track(self) -> Optional['webrtc.MediaStreamTrack']:
        """:obj:`webrtc.MediaStreamTrack`, optional: The :obj:`webrtc.MediaStreamTrack` which is being handled by
        the :obj:`webrtc.RTCRtpSender`. If track is :obj:`None`, the :obj:`webrtc.RTCRtpSender`
        doesn't transmit anything."""
        from webrtc import MediaStreamTrack

        return MediaStreamTrack._wrap_optional(self._native_obj.track)

    @property
    def transport(self) -> Optional['webrtc.RTCDtlsTransport']:
        """:obj:`webrtc.RTCDtlsTransport`, optional: An object representing the underlying transport being used by
        the sender to exchange packets with the remote peer, or :obj:`None` if the sender isn't yet connected
        to transport."""
        from webrtc import RTCDtlsTransport

        return RTCDtlsTransport._wrap_optional(self._native_obj.transport)

    @property
    def dtmf(self) -> Optional['webrtc.RTCDTMFSender']:
        """:obj:`webrtc.RTCDTMFSender`, optional: Sends DTMF tones, for an audio sender."""
        from webrtc import RTCDTMFSender

        return RTCDTMFSender._wrap_optional(self._native_obj.dtmf)

    @property
    def kind(self) -> 'webrtc.MediaType':
        """:obj:`webrtc.MediaType`: The kind of media the sender sends, audio or video."""
        return self._native_obj.kind

    def get_parameters(self) -> 'webrtc.RTCRtpSendParameters':
        """Returns the parameters the sender sends with.

        To change them, modify the returned parameters and pass them to :meth:`set_parameters` before the current
        task of the event loop ends: parameters from an earlier task aren't accepted anymore.

        Returns:
            :obj:`webrtc.RTCRtpSendParameters`: The parameters, with a new ``transaction_id``.
        """
        parameters = RTCRtpSendParameters._from_native(self._native_obj.getParameters())
        if self.kind == MediaType.video:
            _default_scale_resolution_down_by(parameters.encodings)
        # they expire when the current task (with the code it resumed) is over, never without a loop
        TaskQueue.post_to_running(self._native_obj._expireParameters, parameters.transaction_id, after_ready=True)
        return parameters

    async def set_parameters(
        self, parameters: 'webrtc.RTCRtpSendParameters', *, key_frames: Optional[Sequence[bool]] = None
    ) -> None:
        """Changes how the sender sends: its encodings and degradation preference.

        Args:
            parameters (:obj:`webrtc.RTCRtpSendParameters`): The parameters :meth:`get_parameters` returned in the
                current task, modified.
            key_frames (:obj:`list` of :obj:`bool`, optional): For each encoding, whether it sends a key frame
                right away.

        Raises:
            :obj:`webrtc.InvalidStateError`: If :meth:`get_parameters` wasn't called in the current task.
            :obj:`webrtc.InvalidModificationError`: If the ``transaction_id``, the codecs, the header extensions,
                the RTCP parameters, the number of encodings or their ``rid`` changed, the codec of an encoding
                isn't negotiated, or ``key_frames`` isn't one per encoding.
            :obj:`webrtc.InvalidRangeError`: If a value is out of range, like ``scale_resolution_down_by`` below 1.
        """
        if self._native_obj._transceiverStopped():
            raise InvalidStateError('The transceiver of the sender is stopped')
        last = self._native_obj._lastParameters()
        if last is None:
            raise InvalidStateError('get_parameters() must be called before set_parameters(), in the same task')
        self._check_parameters(parameters, last, key_frames)

        kind = self.kind
        # a copy (pybind returns one): changed, then set back
        encodings = last.encodings
        for native, encoding in zip(encodings, parameters.encodings):
            encoding._for_kind(kind)._apply(native)
        for native, key_frame in zip(encodings, key_frames or ()):
            native.requestKeyFrame = bool(key_frame)
        last.encodings = encodings
        last.degradationPreference = parameters.degradation_preference
        await call_native(self._native_obj.setParameters, last)

    async def replace_track(self, track: Optional['webrtc.MediaStreamTrack']) -> None:
        """Replaces the track the sender sends, without negotiation.

        The track is replaced in the operations chain of the connection, after the operations started before
        (like setting a description), and not before the code that called it runs on.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`, optional): The new track, of the same kind, or :obj:`None`
                to stop sending.

        Raises:
            :obj:`TypeError`: If the track is of another kind.
            :obj:`webrtc.InvalidStateError`: If the transceiver of the sender is stopped, or the connection closed.
        """
        from webrtc import RTCPeerConnection

        if track is not None and track.kind != self.kind:
            raise TypeError(f'a {track.kind} track can not replace the track of a {self.kind} sender')

        def replace():
            native_track = track._native_obj if track is not None else None
            if self._native_obj._transceiverStopped() or not self._native_obj.replaceTrack(native_track):
                raise InvalidStateError('The track of a stopped sender can not be replaced')

        connection = wrtc.RTCPeerConnection._connectionOf(self._native_obj)
        if connection is None:
            replace()
            return
        pc = RTCPeerConnection._wrap(connection)
        async with pc._operation():
            pc._check_state('replace the track')
            await later()
            replace()

    def set_streams(self, *streams: 'webrtc.MediaStream') -> None:
        """Sets the streams the remote peer associates the track of the sender with, from the next negotiation.

        Args:
            *streams (:obj:`webrtc.MediaStream`): The streams, none to associate the track with no stream.
        """
        ids = []
        for stream in streams:
            if stream.id not in ids:
                ids.append(stream.id)
        self._native_obj.setStreams(ids)

    @staticmethod
    def get_capabilities(kind: 'webrtc.MediaType') -> Optional['webrtc.RTCRtpCapabilities']:
        """Returns the codecs and header extensions senders of a kind support.

        Args:
            kind (:obj:`webrtc.MediaType`): Audio or video.

        Returns:
            :obj:`webrtc.RTCRtpCapabilities`, optional: The capabilities, :obj:`None` for another kind.
        """
        return RTCRtpCapabilities._supported(wrtc.RTCRtpSender, kind)

    async def get_stats(self) -> 'webrtc.RTCStatsReport':
        """Collects the stats of the sender, and of the objects its stats refer to.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
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


def _default_scale_resolution_down_by(encodings: List['webrtc.RTCRtpEncodingParameters']) -> None:
    """Video encodings without scale_resolution_down_by scale by 1, or by descending powers of 2 if none has one."""
    if all(e.scale_resolution_down_by is None for e in encodings):
        for i, encoding in enumerate(encodings):
            encoding.scale_resolution_down_by = float(2 ** (len(encodings) - 1 - i))
    for encoding in encodings:
        if encoding.scale_resolution_down_by is None:
            encoding.scale_resolution_down_by = 1.0
