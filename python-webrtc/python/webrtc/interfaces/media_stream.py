#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, List, Optional

import wrtc

from webrtc import WebRTCObject, MediaStreamTrack

if TYPE_CHECKING:
    import webrtc


class MediaStream(WebRTCObject):
    """The MediaStream interface represents a stream of media content. A stream consists of several tracks,
    such as video or audio tracks. Each track is specified as an instance of :obj:`webrtc.MediaStreamTrack`.
    """

    _class = wrtc.MediaStream

    @property
    def id(self) -> str:
        """:obj:`str`: A String containing 36 characters denoting a
        universally unique identifier (UUID) for the object."""
        return self._native_obj.id

    @property
    def active(self) -> bool:
        """:obj:`bool`: A value that returns `true` if the :obj:`webrtc.MediaStream` is active, or `false` otherwise."""
        return self._native_obj.active

    def get_audio_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of the :obj:`webrtc.MediaStreamTrack` objects
        stored in the :obj:`webrtc.MediaStream` object that have their kind attribute set to "audio".
        The order is not defined, and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many(self._native_obj.getAudioTracks())

    def get_video_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of the :obj:`webrtc.MediaStreamTrack` objects stored in the :obj:`webrtc.MediaStream`
        object that have their kind attribute set to "video". The order is not defined,
        and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many(self._native_obj.getVideoTracks())

    def get_tracks(self) -> List['webrtc.MediaStreamTrack']:
        """Returns a :obj:`list` of all :obj:`webrtc.MediaStreamTrack` objects stored in the :obj:`webrtc.MediaStream`
        object, regardless of the value of the kind attribute. The order is not defined,
        and may not only vary from one machine to another, but also from one call to another.
        """
        return MediaStreamTrack._wrap_many(self._native_obj.getTracks())

    def get_track_by_id(self, track_id: str) -> Optional['webrtc.MediaStreamTrack']:
        """Returns the track whose ID corresponds to the one given in parameters, :obj:`track_id`.
        If no parameter is given, or if no track with that ID does exist, it returns :obj:`None`.
        If several tracks have the same ID, it returns the first one.
        """
        return MediaStreamTrack._wrap(self._native_obj.getTrackById(track_id))

    def add_track(self, track: 'webrtc.MediaStreamTrack'):
        """Stores a copy of the :obj:`webrtc.MediaStreamTrack` given as argument. If the track has already been added
        to the :obj:`webrtc.MediaStream` object, nothing happens.
        """
        return self._native_obj.addTrack(track._native_obj)

    def remove_track(self, track: 'webrtc.MediaStreamTrack'):
        """Removes the :obj:`webrtc.MediaStreamTrack` given as argument. If the track is not part of the
        :obj:`webrtc.MediaStream` object, nothing happens.
        """
        return self._native_obj.removeTrack(track._native_obj)

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
