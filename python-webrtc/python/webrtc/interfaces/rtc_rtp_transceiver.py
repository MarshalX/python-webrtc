#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCRtpTransceiver of WebRTC."""

from __future__ import annotations

import webrtc
from webrtc import InvalidModificationError, RTCRtpCodec, RTCRtpHeaderExtensionCapability, WebRTCObject, wrtc


class RTCRtpTransceiver(WebRTCObject[wrtc.RTCRtpTransceiver]):
    """A permanent pair of an :obj:`webrtc.RTCRtpSender` and an :obj:`webrtc.RTCRtpReceiver`, with shared state."""

    _class = wrtc.RTCRtpTransceiver

    @property
    def mid(self) -> str | None:
        """A :obj:`str` which uniquely identifies the pairing of source and destination of the transceiver's stream.

        Its value is taken from the media ID of the SDP m-line. This value is :obj:`None` if negotiation has not
        completed.
        """
        return self._native_obj.mid

    @property
    def receiver(self) -> webrtc.RTCRtpReceiver:
        """:obj:`webrtc.RTCRtpReceiver`: Receives and decodes the incoming media of the :attr:`mid`."""
        return webrtc.RTCRtpReceiver._wrap(self._native_obj.receiver)

    @property
    def sender(self) -> webrtc.RTCRtpSender:
        """:obj:`webrtc.RTCRtpSender`: Encodes and sends the media of the :attr:`mid`."""
        return webrtc.RTCRtpSender._wrap(self._native_obj.sender)

    @property
    def stopped(self) -> bool:
        """:obj:`bool`: Whether both the :attr:`sender` and the :attr:`receiver` stopped for good.

        Warning:
            Deprecated: This feature is no longer recommended.
        """
        return self._native_obj.stopped

    @property
    def direction(self) -> webrtc.TransceiverDirection:
        """A member of :obj:`webrtc.TransceiverDirection` enum, indicating the transceiver's preferred direction.

        Note:
            The transceiver's current direction is indicated by the :attr:`currentDirection` property.
        """
        return self._native_obj.direction

    @direction.setter
    def direction(self, new_direction: webrtc.TransceiverDirection | webrtc.TransceiverDirectionValue) -> None:
        self._native_obj.direction = new_direction

    @property
    def current_direction(self) -> webrtc.TransceiverDirection | None:
        """:obj:`webrtc.TransceiverDirection`, optional: The negotiated direction of the transceiver."""
        return self._native_obj.currentDirection

    def stop(self) -> None:
        """Stops the transceiver for good, its :obj:`webrtc.RTCRtpSender` and its :obj:`webrtc.RTCRtpReceiver`.

        Note:
            To check whether the transceiver is stopped, compare :attr:`currentDirection` with
            :obj:`webrtc.TransceiverDirection.stopped` rather than reading the deprecated :attr:`stopped`.
        """
        self._native_obj.stop()

    @property
    def kind(self) -> webrtc.MediaType:
        """:obj:`webrtc.MediaType`: The kind of media the transceiver sends and receives, audio or video."""
        return self._native_obj.kind

    def set_codec_preferences(self, codecs: list[webrtc.RTCRtpCodec]) -> None:
        """Sets the codecs to negotiate, in order of preference, from the next negotiation.

        Args:
            codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodec`): Codecs from the capabilities of
                :meth:`webrtc.RTCRtpSender.get_capabilities` or :meth:`webrtc.RTCRtpReceiver.get_capabilities`
                for the kind of the transceiver. An empty list restores the default preferences.

        Raises:
            webrtc.InvalidModificationError: If a codec isn't supported, or only resiliency codecs
                (like RTX or FEC) are given.
        """
        kind = self.kind
        natives: list[wrtc.RtpCodecCapability] = []
        for source in (wrtc.RTCRtpReceiver.getCapabilities(kind), wrtc.RTCRtpSender.getCapabilities(kind)):
            natives.extend(source.codecs if source is not None else [])

        preferences: list[wrtc.RtpCodecCapability] = []
        for codec in codecs:
            native = next((n for n in natives if RTCRtpCodec._from_native(n)._matches(codec)), None)
            if native is None:
                msg = f'{codec.mime_type} is not a {kind} codec that can be negotiated'
                raise InvalidModificationError(msg)
            preferences.append(native)
        self._native_obj.setCodecPreferences(preferences)

    def get_header_extensions_to_negotiate(self) -> list[webrtc.RTCRtpHeaderExtensionCapability]:
        """Returns the header extensions offered or accepted in the next negotiation.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: The extensions, with the direction they're
            negotiated in, :attr:`webrtc.TransceiverDirection.stopped` for the ones that aren't.
        """
        return [
            RTCRtpHeaderExtensionCapability._from_native(e) for e in self._native_obj.getHeaderExtensionsToNegotiate()
        ]

    def set_header_extensions_to_negotiate(self, extensions: list[webrtc.RTCRtpHeaderExtensionCapability]) -> None:
        """Changes the directions the header extensions are negotiated in, from the next negotiation.

        Args:
            extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`): The list
                :meth:`get_header_extensions_to_negotiate` returns, with directions changed.

        Raises:
            ValueError: If an extension has an empty URI.
            webrtc.InvalidModificationError: If the extensions or their order differ, or a mandatory
                extension is stopped.
        """
        current = {e.uri: e for e in self._native_obj.getHeaderExtensionsToNegotiate()}
        natives: list[wrtc.RtpHeaderExtensionCapability] = []
        for extension in extensions:
            if extension.uri == '':
                msg = 'the URI of a header extension must not be empty'
                raise ValueError(msg)
            native = wrtc.RtpHeaderExtensionCapability()
            native.uri = extension.uri
            if extension.uri in current:
                native.preferredId = current[extension.uri].preferredId
            native.direction = extension.direction
            natives.append(native)
        self._native_obj.setHeaderExtensionsToNegotiate(natives)

    def get_negotiated_header_extensions(self) -> list[webrtc.RTCRtpHeaderExtensionCapability]:
        """Returns the header extensions negotiated last, and their directions.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: Every extension that can be negotiated,
            :attr:`webrtc.TransceiverDirection.stopped` for the ones that weren't.
        """
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
