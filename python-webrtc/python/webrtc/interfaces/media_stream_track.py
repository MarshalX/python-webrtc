#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

from webrtc import WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc


class MediaStreamTrack(WebRTCObject, EventTarget):
    """The MediaStreamTrack interface represents a single media track within a stream;
    typically, these are audio or video tracks, but other track types may exist as well.

    Events (see :meth:`on`):
        ``mute`` and ``unmute`` (:obj:`webrtc.Event`): :attr:`muted` changed: a remote track is muted until media
        arrives, and when it's no longer negotiated.
        ``ended`` (:obj:`webrtc.Event`): The track ended, other than with :meth:`stop`, like when the remote peer
        stopped sending it.
    """

    _class = wrtc.MediaStreamTrack
    _events = ('mute', 'unmute', 'ended')

    def _on_event(self, name: str, *args):
        # muted changes along with the events
        if name in ('mute', 'unmute'):
            (muted,) = args
            self._native_obj._surfaceMuted(muted)
        elif name == 'ended':
            self._native_obj._surfaceEnded()

    @property
    def enabled(self) -> bool:
        """:obj:`bool`: A Boolean whose value of true if the track is enabled, that is allowed to render
        the media source stream; or false if it is disabled, that is not rendering the media source stream but silence
        and blackness. If the track has been disconnected, this value can be changed but has no more effect."""
        return self._native_obj.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._native_obj.enabled = value

    @property
    def id(self) -> str:
        """:obj:`str`: A unique identifier (GUID) for the track."""
        return self._native_obj.id

    @property
    def label(self) -> str:
        """:obj:`str`: The label of the source, ``'remote audio'`` or ``'remote video'`` for a remote track."""
        return self._native_obj.label

    @property
    def kind(self) -> 'webrtc.MediaType':
        """:obj:`webrtc.MediaType`: Indicating type of media. Audio or video. It doesn't change if the track is
        deassociated from its source."""
        return self._native_obj.kind

    @property
    def ready_state(self) -> 'webrtc.MediaStreamTrackState':
        """:obj:`webrtc.MediaStreamTrackState`: Returns an enumerated value giving the status of the track."""
        return self._native_obj.readyState

    @property
    def muted(self) -> bool:
        """:obj:`bool`: A value indicating whether the track
        is unable to provide media data due to a technical issue."""
        return self._native_obj.muted

    def clone(self) -> 'webrtc.MediaStreamTrack':
        """Returns a duplicate of the :obj:`webrtc.MediaStreamTrack`."""
        return self._wrap(self._native_obj.clone())

    def stop(self):
        """Stops playing the source associated to the track, both the source and the track are deassociated.
        The track state is set to ended."""
        return self._native_obj.stop()

    #: Alias for :attr:`ready_state`
    readyState = ready_state
