#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, List, Optional

from webrtc import WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RTCRtpTransceiver(WebRTCObject):
    """The WebRTC interface :obj:`webrtc.RTCRtpTransceiver` describes a permanent pairing of
    an :obj:`webrtc.RTCRtpSender` and an :obj:`webrtc.RTCRtpReceiver`, along with some shared state.
    """

    _class = wrtc.RTCRtpTransceiver

    @property
    def mid(self) -> Optional[str]:
        """A :obj:`str` which uniquely identifies the pairing of source and destination of the transceiver's stream.
        Its value is taken from the media ID of the SDP m-line. This value is :obj:`None` if negotiation
        has not completed."""
        return self._native_obj.mid

    @property
    def receiver(self) -> 'webrtc.RTCRtpReceiver':
        """A :obj:`webrtc.RTCRtpReceiver` object which is responsible for receiving and decoding incoming media data
        whose media ID is the same as the current value of :attr:`mid`."""
        from webrtc import RTCRtpReceiver

        return RTCRtpReceiver._wrap(self._native_obj.receiver)

    @property
    def sender(self) -> 'webrtc.RTCRtpSender':
        """A :obj:`webrtc.RTCRtpSender` object used to encode and send media whose media ID matches
        the current value of :attr:`mid`."""
        from webrtc import RTCRtpSender

        return RTCRtpSender._wrap(self._native_obj.sender)

    @property
    def stopped(self) -> bool:
        """A :obj:`bool` value which is :obj:`True` if the transceiver's :attr:`sender` will no longer send data,
        and its :attr:`receiver` will no longer receive data. If either or both are still at work,
        the result is :obj:`False`.

        Warning:
            Deprecated: This feature is no longer recommended.
        """
        return self._native_obj.stopped

    @property
    def direction(self) -> 'webrtc.TransceiverDirection':
        """A member of :obj:`webrtc.TransceiverDirection` enum, indicating the transceiver's preferred direction.

        Note:
            The transceiver's current direction is indicated by the :attr:`currentDirection` property.
        """
        return self._native_obj.direction

    @direction.setter
    def direction(self, new_direction: 'webrtc.TransceiverDirection'):
        self._native_obj.direction = new_direction

    @property
    def current_direction(self) -> Optional['webrtc.TransceiverDirection']:
        """A member of :obj:`webrtc.TransceiverDirection` enum, indicating
        the current directionality of the transceiver."""
        return self._native_obj.currentDirection

    def stop(self) -> None:
        """Permanently stops the transceiver by stopping both the associated :obj:`webrtc.RTCRtpSender`
        and :obj:`webrtc.RTCRtpReceiver`.

        Note:
            The :attr:`stopped` property was provided to return :obj:`True` if the connection is stopped.
            That property has been deprecated and will be removed at some point. Instead, check the value
            of :attr:`currentDirection`. If it's :obj:`webrtc.TransceiverDirection.stopped`, the transceiver
            has been stopped.
        """
        self._native_obj.stop()

    @property
    def kind(self) -> 'webrtc.MediaType':
        """:obj:`webrtc.MediaType`: Whether the transceiver sends and receives audio or video."""
        return self._native_obj.kind

    def set_codec_preferences(self, codecs: List['webrtc.RTCRtpCodec']) -> None:
        """Sets the codecs to negotiate, in order of preference, from the next negotiation.

        Args:
            codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodec`): Codecs from the capabilities of
                :meth:`webrtc.RTCRtpSender.get_capabilities` or :meth:`webrtc.RTCRtpReceiver.get_capabilities`
                for the kind of the transceiver. An empty list restores the default preferences.

        Raises:
            :obj:`webrtc.InvalidModificationError`: If a codec isn't supported, or only resiliency codecs
                (like RTX or FEC) are given.
        """
        from webrtc import InvalidModificationError, RTCRtpCodec

        kind = self.kind.name
        natives = []
        for source in (wrtc.RTCRtpReceiver.getCapabilities(kind), wrtc.RTCRtpSender.getCapabilities(kind)):
            natives.extend(source.codecs if source is not None else [])

        preferences = []
        for codec in codecs:
            native = next((n for n in natives if RTCRtpCodec._from_native(n)._matches(codec)), None)
            if native is None:
                raise InvalidModificationError(f'{codec.mime_type} is not a {kind} codec that can be negotiated')
            preferences.append(native)
        self._native_obj.setCodecPreferences(preferences)

    def get_header_extensions_to_negotiate(self) -> List['webrtc.RTCRtpHeaderExtensionCapability']:
        """Returns the header extensions offered or accepted in the next negotiation.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: The extensions, with the direction they're
            negotiated in, :attr:`webrtc.TransceiverDirection.stopped` for the ones that aren't.
        """
        from webrtc import RTCRtpHeaderExtensionCapability

        return [
            RTCRtpHeaderExtensionCapability._from_native(e) for e in self._native_obj.getHeaderExtensionsToNegotiate()
        ]

    def set_header_extensions_to_negotiate(self, extensions: List['webrtc.RTCRtpHeaderExtensionCapability']) -> None:
        """Changes the directions the header extensions are negotiated in, from the next negotiation.

        Args:
            extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`): The list
                :meth:`get_header_extensions_to_negotiate` returns, with directions changed.

        Raises:
            :obj:`ValueError`: If an extension has an empty URI.
            :obj:`webrtc.InvalidModificationError`: If the extensions or their order differ, or a mandatory
                extension is stopped.
        """
        current = {e.uri: e for e in self._native_obj.getHeaderExtensionsToNegotiate()}
        natives = []
        for extension in extensions:
            if not extension.uri:
                raise ValueError('the URI of a header extension must not be empty')
            native = wrtc.RtpHeaderExtensionCapability()
            native.uri = extension.uri
            if extension.uri in current:
                native.preferredId = current[extension.uri].preferredId
            native.direction = extension.direction
            natives.append(native)
        self._native_obj.setHeaderExtensionsToNegotiate(natives)

    def get_negotiated_header_extensions(self) -> List['webrtc.RTCRtpHeaderExtensionCapability']:
        """Returns the header extensions negotiated last, and their directions.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: Every extension that can be negotiated,
            :attr:`webrtc.TransceiverDirection.stopped` for the ones that weren't.
        """
        from webrtc import RTCRtpHeaderExtensionCapability

        return [
            RTCRtpHeaderExtensionCapability._from_native(e) for e in self._native_obj.getNegotiatedHeaderExtensions()
        ]

    #: Alias for :attr:`current_direction`
    currentDirection = current_direction
    #: Alias for :attr:`set_codec_preferences`
    setCodecPreferences = set_codec_preferences
    #: Alias for :attr:`get_header_extensions_to_negotiate`
    getHeaderExtensionsToNegotiate = get_header_extensions_to_negotiate
    #: Alias for :attr:`set_header_extensions_to_negotiate`
    setHeaderExtensionsToNegotiate = set_header_extensions_to_negotiate
    #: Alias for :attr:`get_negotiated_header_extensions`
    getNegotiatedHeaderExtensions = get_negotiated_header_extensions
