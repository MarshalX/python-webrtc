#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The pair of a sender and a receiver that share a media section of the SDP."""

from __future__ import annotations

import webrtc
from webrtc import InvalidModificationError, RTCRtpCodec, RTCRtpHeaderExtensionCapability, WebRTCObject, wrtc


class RTCRtpTransceiver(WebRTCObject[wrtc.RTCRtpTransceiver]):
    """A sender and a receiver that share one media section of the SDP, with its direction and codecs.

    Created by :meth:`webrtc.RTCPeerConnection.add_transceiver`, :meth:`webrtc.RTCPeerConnection.add_track` and
    remote offers, and listed by :meth:`webrtc.RTCPeerConnection.get_transceivers`. See :mdn:`RTCRtpTransceiver`.
    """

    _class = wrtc.RTCRtpTransceiver

    @property
    def mid(self) -> str | None:
        """:obj:`str`, optional: The media ID (``a=mid``) of the media section of the transceiver.

        :obj:`None` until a description with the section is set. See :mdn:`RTCRtpTransceiver/mid`.
        """
        return self._native_obj.mid

    @property
    def receiver(self) -> webrtc.RTCRtpReceiver:
        """:obj:`webrtc.RTCRtpReceiver`: Receives and decodes the media of the transceiver. It's always the same object.

        See :mdn:`RTCRtpTransceiver/receiver`.
        """
        return webrtc.RTCRtpReceiver._wrap(self._native_obj.receiver)

    @property
    def sender(self) -> webrtc.RTCRtpSender:
        """:obj:`webrtc.RTCRtpSender`: Encodes and sends the media of the transceiver. It's always the same object.

        See :mdn:`RTCRtpTransceiver/sender`.
        """
        return webrtc.RTCRtpSender._wrap(self._native_obj.sender)

    @property
    def stopped(self) -> bool:
        """:obj:`bool`: Whether the transceiver was stopped, by :meth:`stop` or by a negotiation.

        See :mdn:`RTCRtpTransceiver/stopped`.

        Warning:
            Deprecated. Compare :attr:`current_direction` with :obj:`webrtc.RTCRtpTransceiverDirection.stopped`.
        """
        return self._native_obj.stopped

    @property
    def direction(self) -> webrtc.RTCRtpTransceiverDirection:
        """:obj:`webrtc.RTCRtpTransceiverDirection`: The preferred direction, which the next negotiation offers.

        It can be set with a member or its value. A change leads to a ``negotiationneeded`` event, and the negotiated
        direction is :attr:`current_direction`. Setting it on a stopped transceiver raises
        :obj:`webrtc.InvalidStateError`. Setting it to ``stopped`` raises :obj:`webrtc.InvalidAccessError`, so use
        :meth:`stop` for that. See :mdn:`RTCRtpTransceiver/direction`.
        """
        return self._native_obj.direction

    @direction.setter
    def direction(
        self, new_direction: webrtc.RTCRtpTransceiverDirection | webrtc.RTCRtpTransceiverDirectionValue
    ) -> None:
        self._native_obj.direction = new_direction

    @property
    def current_direction(self) -> webrtc.RTCRtpTransceiverDirection | None:
        """:obj:`webrtc.RTCRtpTransceiverDirection`, optional: The direction of the last negotiation.

        :obj:`None` until the transceiver is negotiated. See :mdn:`RTCRtpTransceiver/currentDirection`.
        """
        return self._native_obj.currentDirection

    def stop(self) -> None:
        """Stops the transceiver for good. Its sender stops sending and the track of its receiver ends.

        The next negotiation removes its media section. See :mdn:`RTCRtpTransceiver/stop`.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
        """
        self._native_obj.stop()

    @property
    def _kind(self) -> webrtc.MediaType:
        # the kind of the native object, which the receiver's track has too
        return self._native_obj.kind

    def set_codec_preferences(self, codecs: list[webrtc.RTCRtpCodec]) -> None:
        """Sets the codecs to negotiate, in order of preference, from the next negotiation.

        Codecs are matched to the supported ones by MIME type, clock rate, channels and SDP format parameters.
        See :mdn:`RTCRtpTransceiver/setCodecPreferences`.

        Args:
            codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodec`): Codecs from the capabilities of
                :meth:`webrtc.RTCRtpSender.get_capabilities` or :meth:`webrtc.RTCRtpReceiver.get_capabilities`
                for the kind of the transceiver. An empty list restores the default preferences.

        Raises:
            webrtc.InvalidModificationError: If a codec isn't supported, or only resiliency codecs
                (like RTX or FEC) are given.
        """
        kind = self._kind
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
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: The extensions and the direction each one
            is negotiated in. The ones that aren't negotiated have :attr:`webrtc.RTCRtpTransceiverDirection.stopped`.
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
            TypeError: If an extension has an empty URI.
            webrtc.InvalidModificationError: If the extensions or their order differ, or a mandatory
                extension is stopped.
        """
        current = {e.uri: e for e in self._native_obj.getHeaderExtensionsToNegotiate()}
        natives: list[wrtc.RtpHeaderExtensionCapability] = []
        for extension in extensions:
            if extension.uri == '':
                msg = 'the URI of a header extension must not be empty'
                raise TypeError(msg)
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
            :obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`: Every extension that can be negotiated.
            The ones that weren't negotiated have :attr:`webrtc.RTCRtpTransceiverDirection.stopped`.
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
