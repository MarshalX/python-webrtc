#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, List, Optional, Union

from webrtc import MediaStreamTrack, MediaStreamTrackEvent, MediaType, WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc


class MediaStream(WebRTCObject, EventTarget):
    """The MediaStream interface represents a stream of media content. A stream consists of several tracks,
    such as video or audio tracks. Each track is specified as an instance of :obj:`webrtc.MediaStreamTrack`.

    Events (see :meth:`on`):
        ``addtrack`` and ``removetrack`` (:obj:`webrtc.MediaStreamTrackEvent`): The remote peer added a track to
        a remote stream, or removed one. Changes made with :meth:`add_track` and :meth:`remove_track` fire none.

    Args:
        tracks (:obj:`list` of :obj:`webrtc.MediaStreamTrack`, optional): The tracks of the new stream,
            or a stream whose tracks the new stream shares.
    """

    _class = wrtc.MediaStream
    _events = ('addtrack', 'removetrack')

    def __init__(self, tracks: Optional[Union[List['webrtc.MediaStreamTrack'], 'webrtc.MediaStream']] = None):
        if isinstance(tracks, MediaStream):
            tracks = tracks.get_tracks()
        super().__init__(self._class.create([track._native_obj for track in tracks or []]))
        self._keep_tracks()

    @classmethod
    def _wrap(cls, item) -> 'MediaStream':
        stream = super()._wrap(item)
        stream._keep_tracks()
        return stream

    def _keep_tracks(self) -> list:
        """The native tracks, kept here: the native stream keeps them weakly"""
        self._tracks = self._native_obj.getTracks()
        return self._tracks

    def _on_event(self, name: str, *args):
        if name in ('addtrack', 'removetrack'):
            self._keep_tracks()

    def _create_event(self, name: str, *args):
        (track,) = args
        return MediaStreamTrackEvent(name, MediaStreamTrack._wrap(track), target=self)

    @property
    def id(self) -> str:
        """:obj:`str`: A String containing 36 characters denoting a
        universally unique identifier (UUID) for the object."""
        return self._native_obj.id

    @property
    def active(self) -> bool:
        """:obj:`bool`: Whether the :obj:`webrtc.MediaStream` is active: whether a track of it isn't ended."""
        return self._native_obj.active

    def get_audio_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of the :obj:`webrtc.MediaStreamTrack` objects
        stored in the :obj:`webrtc.MediaStream` object that have their kind attribute set to "audio".
        The order is not defined, and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many([t for t in self._keep_tracks() if t.kind == MediaType.audio])

    def get_video_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of the :obj:`webrtc.MediaStreamTrack` objects stored in the :obj:`webrtc.MediaStream`
        object that have their kind attribute set to "video". The order is not defined,
        and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many([t for t in self._keep_tracks() if t.kind == MediaType.video])

    def get_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of all :obj:`webrtc.MediaStreamTrack` objects stored in the :obj:`webrtc.MediaStream`
        object, regardless of the value of the kind attribute. The order is not defined,
        and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many(self._keep_tracks())

    def get_track_by_id(self, track_id: str) -> Optional['webrtc.MediaStreamTrack']:
        """Returns the track whose ID corresponds to the one given in parameters, :obj:`track_id`.
        If no track with that ID does exist, it returns :obj:`None`.
        If several tracks have the same ID, it returns the first one.
        """
        track = self._native_obj.getTrackById(track_id)
        self._keep_tracks()
        return MediaStreamTrack._wrap_optional(track)

    def add_track(self, track: 'webrtc.MediaStreamTrack'):
        """Stores a copy of the :obj:`webrtc.MediaStreamTrack` given as argument. If the track has already been added
        to the :obj:`webrtc.MediaStream` object, nothing happens.
        """
        self._native_obj.addTrack(track._native_obj)
        self._keep_tracks()

    def remove_track(self, track: 'webrtc.MediaStreamTrack'):
        """Removes the :obj:`webrtc.MediaStreamTrack` given as argument. If the track is not part of the
        :obj:`webrtc.MediaStream` object, nothing happens.
        """
        self._native_obj.removeTrack(track._native_obj)
        self._keep_tracks()

    def clone(self) -> 'webrtc.MediaStream':
        """Returns a clone of the :obj:`webrtc.MediaStream` object.
        The clone will, however, have a unique value for :obj:`id`."""
        return self._wrap(self._native_obj.clone())

    #: Alias for :attr:`get_audio_tracks`
    getAudioTracks = get_audio_tracks
    #: Alias for :attr:`get_video_tracks`
    getVideoTracks = get_video_tracks
    #: Alias for :attr:`get_tracks`
    getTracks = get_tracks
    #: Alias for :attr:`get_track_by_id`
    getTrackById = get_track_by_id
    #: Alias for :attr:`add_track`
    addTrack = add_track
    #: Alias for :attr:`remove_track`
    removeTrack = remove_track
