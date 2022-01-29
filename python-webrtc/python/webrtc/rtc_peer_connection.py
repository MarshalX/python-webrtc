import wrtc

from .utils.callback_to_async import to_async


class RTCPeerConnection:
    """The RTCPeerConnection interface represents a WebRTC connection between the local computer and a remote peer.
        It provides methods to connect to a remote peer, maintain and monitor the connection, and close the connection
        once it's no longer needed.

    """

    def __init__(self):
        self.__pc = wrtc.RTCPeerConnection()

    async def set_local_description(self, sdp):
        """Changes the local description associated with the connection. This description specifies the properties
        of the local end of the connection, including the media format. It returns an awaitable which is fulfilled
        once the description has been changed, asynchronously.

        """
        return await to_async(self.__pc.setLocalDescription)(sdp)

    async def set_remote_description(self, sdp):
        """Sets the specified session description as the remote peer's current offer or answer. The description
        specifies the properties of the remote end of the connection, including the media format.
        It returns an awaitable which is fulfilled once the description has been changed, asynchronously.

        """
        return await to_async(self.__pc.setRemoteDescription)(sdp)

    async def create_offer(self):
        """Initiates the creation of an SDP offer for the purpose of starting a new WebRTC connection to a remote peer.
        The SDP offer includes information about any MediaStreamTrack objects already attached to the WebRTC session,
        codec, and options supported by the browser, as well as any candidates already gathered by the ICE agent, for
        the purpose of being sent over the signaling channel to a potential peer to request a connection or to update
        the configuration of an existing connection.

        """
        return await to_async(self.__pc.createOffer)

    async def add_track(self, track, stream=None):
        """Adds a new MediaStreamTrack to the set of tracks which will be transmitted to the other peer.

        """
        return self.__pc.addTrack(track, stream)

    #: Alias for :attr:`set_local_description`
    setLocalDescription = set_local_description
    #: Alias for :attr:`set_remote_description`
    setRemoteDescription = set_remote_description
    #: Alias for :attr:`create_offer`
    createOffer = create_offer
    #: Alias for :attr:`add_track`
    addTrack = add_track
