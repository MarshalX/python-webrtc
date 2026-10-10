#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStream of Media Capture and Streams, which groups tracks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from typing_extensions import override

import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import MediaType
from webrtc.interfaces.media_stream_track import MediaStreamTrack
from webrtc.models.events import MediaStreamTrackEvent, MediaStreamTrackEventInit
from webrtc.utils.events import UniformEventTarget

if TYPE_CHECKING:
    from typing_extensions import Self

    import webrtc


class MediaStream(
    WebRTCObject[wrtc.MediaStream], UniformEventTarget[Literal['addtrack', 'removetrack'], MediaStreamTrackEvent]
):
    """A group of audio and video tracks, played or sent together.

    The stream keeps its tracks alive.

    See :mdn:`MediaStream`.

    Events:
        addtrack and removetrack (:obj:`webrtc.MediaStreamTrackEvent`): The remote peer added a track to
            a remote stream, or removed one. Changes made with :meth:`add_track` and :meth:`remove_track` fire none.

    Args:
        tracks (:obj:`list` of :obj:`webrtc.MediaStreamTrack`, optional): The tracks of the new stream,
            or a stream whose tracks the new stream shares.
    """

    __slots__ = ('_tracks',)

    _class = wrtc.MediaStream
    #: The native tracks, kept alive here because the native stream holds them weakly
    _tracks: list[wrtc.MediaStreamTrack]

    def __init__(self, tracks: list[webrtc.MediaStreamTrack] | webrtc.MediaStream | None = None) -> None:
        if isinstance(tracks, MediaStream):
            tracks = tracks.get_tracks()
        super().__init__(wrtc.MediaStream.create([track._native_obj for track in tracks] if tracks is not None else []))
        self._keep_tracks()

    @classmethod
    @override
    def _wrap(cls, item: wrtc.MediaStream, *, connection: webrtc.RTCPeerConnection | None = None) -> Self:
        stream = super()._wrap(item, connection=connection)
        stream._keep_tracks()
        return stream

    def _keep_tracks(self) -> None:
        self._tracks = self._native_obj.getTracks()

    def _kept_tracks(self) -> list[wrtc.MediaStreamTrack]:
        self._keep_tracks()
        return self._tracks

    def _wrap_track(self, track: wrtc.MediaStreamTrack) -> webrtc.MediaStreamTrack:
        # only remote tracks are children of the stream's connection
        return MediaStreamTrack._wrap(track, connection=self._connection if track._remote else None)

    @override
    def _on_event(self, name: str, *_args: object) -> None:
        if name in {'addtrack', 'removetrack'}:
            self._keep_tracks()

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        (track,) = cast('tuple[wrtc.MediaStreamTrack]', args)
        return MediaStreamTrackEvent(name, MediaStreamTrackEventInit(self._wrap_track(track)))

    @override
    def _activity(self) -> str | None:
        connection = self._connection
        if connection is None or connection._is_closed() or len(self.event_names()) == 0:
            return None
        return 'remote with handlers'

    @property
    def id(self) -> str:
        """:obj:`str`: The ID of the stream. A local stream gets a random UUID and a remote one keeps its peer's ID.

        See :mdn:`MediaStream/id`.
        """
        return self._native_obj.id

    @property
    def active(self) -> bool:
        """:obj:`bool`: Whether a track of the stream hasn't ended yet.

        See :mdn:`MediaStream/active`.
        """
        return self._native_obj.active

    def get_audio_tracks(self) -> list[webrtc.MediaStreamTrack]:
        """Returns the audio tracks of the stream, in no defined order.

        See :mdn:`MediaStream/getAudioTracks`.

        Returns:
            :obj:`list` of :obj:`webrtc.MediaStreamTrack`: The tracks.
        """
        return [self._wrap_track(t) for t in self._kept_tracks() if t.kind == MediaType.audio]

    def get_video_tracks(self) -> list[webrtc.MediaStreamTrack]:
        """Returns the video tracks of the stream, in no defined order.

        See :mdn:`MediaStream/getVideoTracks`.

        Returns:
            :obj:`list` of :obj:`webrtc.MediaStreamTrack`: The tracks.
        """
        return [self._wrap_track(t) for t in self._kept_tracks() if t.kind == MediaType.video]

    def get_tracks(self) -> list[webrtc.MediaStreamTrack]:
        """Returns all the tracks of the stream, in no defined order.

        See :mdn:`MediaStream/getTracks`.

        Returns:
            :obj:`list` of :obj:`webrtc.MediaStreamTrack`: The tracks.
        """
        return [self._wrap_track(t) for t in self._kept_tracks()]

    def get_track_by_id(self, track_id: str) -> webrtc.MediaStreamTrack | None:
        """Returns the track with an ID, the first one if several tracks have it.

        See :mdn:`MediaStream/getTrackById`.

        Args:
            track_id (:obj:`str`): The ID.

        Returns:
            :obj:`webrtc.MediaStreamTrack`, optional: The track, :obj:`None` if no track has the ID.
        """
        track = self._native_obj.getTrackById(track_id)
        self._keep_tracks()
        return self._wrap_track(track) if track is not None else None

    def add_track(self, track: webrtc.MediaStreamTrack) -> None:
        """Adds a track to the stream, unless it's there already. Fires no ``addtrack`` event.

        See :mdn:`MediaStream/addTrack`.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`): The track.
        """
        self._native_obj.addTrack(track._native_obj)
        self._keep_tracks()

    def remove_track(self, track: webrtc.MediaStreamTrack) -> None:
        """Removes a track from the stream, if it's there. Fires no ``removetrack`` event.

        See :mdn:`MediaStream/removeTrack`.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`): The track.
        """
        self._native_obj.removeTrack(track._native_obj)
        self._keep_tracks()

    def clone(self) -> webrtc.MediaStream:
        """Returns a copy of the stream with a new :attr:`id`, holding clones of its tracks.

        See :mdn:`MediaStream/clone`.

        Returns:
            :obj:`webrtc.MediaStream`: The clone.
        """
        return MediaStream([track.clone() for track in self.get_tracks()])

    #: Alias for :meth:`get_audio_tracks`
    getAudioTracks = get_audio_tracks
    #: Alias for :meth:`get_video_tracks`
    getVideoTracks = get_video_tracks
    #: Alias for :meth:`get_tracks`
    getTracks = get_tracks
    #: Alias for :meth:`get_track_by_id`
    getTrackById = get_track_by_id
    #: Alias for :meth:`add_track`
    addTrack = add_track
    #: Alias for :meth:`remove_track`
    removeTrack = remove_track
