#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional, Union, List

import wrtc

from webrtc import WebRTCObject
from webrtc.utils.callback_to_async import to_async

if TYPE_CHECKING:
    import webrtc


class RTCPeerConnection(WebRTCObject):
    """The RTCPeerConnection interface represents a WebRTC connection between the local computer and a remote peer.
        It provides methods to connect to a remote peer, maintain and monitor the connection, and close the connection
        once it's no longer needed.
    """
    _class = wrtc.RTCPeerConnection

    async def create_offer(self):
        """Initiates the creation of an SDP offer for the purpose of starting a new WebRTC connection to a remote peer.
        The SDP offer includes information about any MediaStreamTrack objects already attached to the WebRTC session,
        codec, and options supported by the machine, as well as any candidates already gathered by the ICE agent, for
        the purpose of being sent over the signaling channel to a potential peer to request a connection or to update
        the configuration of an existing connection.
        """
        from webrtc import RTCSessionDescription
        return RTCSessionDescription._wrap(await to_async(self._native_obj.createOffer))

    async def create_answer(self):
        """Initiates the creation an SDP answer to an offer received from a remote peer during the offer/answer
        negotiation of a WebRTC connection. The answer contains information about any media already attached to the
        session, codecs and options supported by the machine, and any ICE candidates already gathered.
        """
        from webrtc import RTCSessionDescription
        return RTCSessionDescription._wrap(await to_async(self._native_obj.createAnswer))

    # TODO arg should be RTCSessionDescriptionInit
    async def set_local_description(self, sdp: 'webrtc.RTCSessionDescription'):
        """Changes the local description associated with the connection. This description specifies the properties
        of the local end of the connection, including the media format. It returns a :obj:`Coroutine`. A result will be
        returned once the description has been changed, asynchronously.

        Args:
            sdp (:obj:`webrtc.RTCSessionDescription`): A :obj:`webrtc.RTCSessionDescription` object that describes
                one end of a connection or potential connection.

        Returns:
            :obj:`None`:
        """
        return await to_async(self._native_obj.setLocalDescription)(sdp._native_obj)

    # TODO arg should be RTCSessionDescriptionInit
    async def set_remote_description(self, sdp: 'webrtc.RTCSessionDescription'):
        """Sets the specified session description as the remote peer's current offer or answer. The description
        specifies the properties of the remote end of the connection, including the media format.
        It returns a :obj:`Coroutine`. A result will be returned once the description has been changed, asynchronously.

        Args:
            sdp (:obj:`webrtc.RTCSessionDescription`): A :obj:`webrtc.RTCSessionDescription` object that describes
                one end of a connection or potential connection.

        Returns:
            :obj:`None`:
        """
        return await to_async(self._native_obj.setRemoteDescription)(sdp._native_obj)

    def add_track(
            self,
            track: 'webrtc.MediaStreamTrack',
            stream: Optional[Union['webrtc.MediaStream', List['webrtc.MediaStream']]] = None
    ) -> 'webrtc.RTCRtpSender':
        """Adds a new :obj:`webrtc.MediaStreamTrack` to the set of tracks which will be transmitted to the other peer.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`): A :obj:`webrtc.MediaStreamTrack` object representing the media track
                to add to the peer connection.
            stream (:obj:`webrtc.MediaStream` or :obj:`list` of :obj:`webrtc.MediaStream`, optional): One or more
                local :obj:`webrtc.MediaStream` objects to which the track should be added.

        Returns:
            :obj:`webrtc.RTCRtpSender`: The :obj:`webrtc.RTCRtpSender` object which will be used to
                transmit the media data.
        """
        if not stream:
            sender = self._native_obj.addTrack(track._native_obj, None)
        elif isinstance(stream, list):
            native_objects = [s._native_obj for s in stream]
            sender = self._native_obj.addTrack(track._native_obj, native_objects)
        else:
            sender = self._native_obj.addTrack(track._native_obj, stream._native_obj)

        from webrtc import RTCRtpSender
        return RTCRtpSender._wrap(sender)

    def close(self):
        """Closes the current peer connection."""
        return self._native_obj.close()

    #: Alias for :attr:`create_offer`
    createOffer = create_offer
    #: Alias for :attr:`create_answer`
    createAnswer = create_answer
    #: Alias for :attr:`set_local_description`
    setLocalDescription = set_local_description
    #: Alias for :attr:`set_remote_description`
    setRemoteDescription = set_remote_description
    #: Alias for :attr:`add_track`
    addTrack = add_track
