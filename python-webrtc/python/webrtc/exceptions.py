#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Exceptions raised by WebRTC operations.

Errors of the specifications are subclasses of :obj:`RTCException`, named after the ``DOMException`` names, so an
``InvalidStateError`` is caught with ``except webrtc.InvalidStateError``. The ``SyntaxError`` and ``RangeError`` of the
specifications are :obj:`InvalidSyntaxError` and :obj:`InvalidRangeError`, which don't shadow the Python builtins and
are :obj:`ValueError` subclasses too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from webrtc import RTCErrorDetailType, wrtc
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.enums import RTCErrorDetailTypeValue

#: The root of every exception of the native module, :obj:`PythonWebRTCException` and :obj:`SdpParseException`
PythonWebRTCExceptionBase = wrtc.PythonWebRTCExceptionBase
#: The native exception that :obj:`RTCException` subclasses, and so every WebRTC error of this library does too
PythonWebRTCException = wrtc.PythonWebRTCException
#: The native exception for an SDP that doesn't parse. Descriptions that don't parse raise :obj:`RTCError` instead,
#: with the ``sdp-syntax-error`` detail
SdpParseException = wrtc.SdpParseException


class RTCException(PythonWebRTCException):
    """The base class of the WebRTC errors. It stands for the ``DOMException`` of the specifications.

    Errors of the native WebRTC engine are raised as the subclass that matches their type. Catch this class to handle
    any of them.

    See :mdn:`DOMException`.
    """

    @property
    def message(self) -> str:
        """:obj:`str`: The description of the error. It's the first argument, or an empty string without one.

        See :mdn:`DOMException/message`.
        """
        return str(self.args[0]) if len(self.args) > 0 else ''


class InvalidStateError(RTCException):
    """The object's state doesn't allow the operation, like calling a method of a closed connection."""


class InvalidAccessError(RTCException):
    """The object doesn't support the parameter or the operation, like a description it can't apply."""


class InvalidModificationError(RTCException):
    """The change isn't allowed, like a change to a read-only member of the parameters of a sender."""


class OperationError(RTCException):
    """The operation failed for a reason specific to it.

    Errors of the native WebRTC engine without a closer match are raised as this class.
    """


class NotSupportedError(RTCException):
    """This library or the native WebRTC engine doesn't support the operation or the value."""


class NetworkError(RTCException):
    """A network protocol below the operation failed."""


class NotFoundError(RTCException):
    """The object asked for doesn't exist, like a simulcast layer of an unknown ``rid``."""


class NotAllowedError(RTCException):
    """The operation isn't allowed with these arguments, like a malformed ``rid``."""


class DataCloneError(RTCException):
    """An object can't be cloned or transferred, like a buffer listed twice in ``transfer``."""


class InvalidSyntaxError(RTCException, ValueError):
    """A string doesn't parse, like an ICE server URL. It stands for the ``SyntaxError`` of the specifications."""


class InvalidRangeError(RTCException, ValueError):
    """A value is out of its allowed range. It stands for the ``RangeError`` of the specifications."""


class InvalidCharacterError(RTCException, ValueError):
    """A string has a character that isn't allowed, like a DTMF tone that doesn't exist."""


class OverconstrainedError(RTCException):
    """No source can satisfy a required constraint of a track.

    See :mdn:`OverconstrainedError`.

    Args:
        constraint (:obj:`str`): The name of the constraint, like ``'width'``.
        message (:obj:`str`, optional): The description of the error. Defaults to one naming the constraint.

    Attributes:
        constraint (:obj:`str`): The name of the constraint that can't be satisfied.
            See :mdn:`OverconstrainedError/constraint`.
    """

    def __init__(self, constraint: str, message: str = '') -> None:
        super().__init__(message if message != '' else f"The constraint {constraint} can't be satisfied")
        self.constraint = constraint


@dataclass
class RTCErrorInit(Dictionary):
    """The WebRTC-specific members of an :obj:`RTCError`.

    See :mdn:`RTCError/RTCError`.

    Args:
        error_detail (:obj:`webrtc.RTCErrorDetailType`): The cause of the error, as a member or its string value.
        sdp_line_number (:obj:`int`, optional): The line of the SDP that doesn't parse.
        sctp_cause_code (:obj:`int`, optional): The SCTP cause code of a failed data channel or association.
        received_alert (:obj:`int`, optional): The DTLS alert received from the remote peer.
        sent_alert (:obj:`int`, optional): The DTLS alert sent to the remote peer.
        http_request_status_code (:obj:`int`, optional): The HTTP status code of a failed request.

    Raises:
        ValueError: If ``error_detail`` isn't a member of :obj:`webrtc.RTCErrorDetailType`.
    """

    error_detail: RTCErrorDetailType | RTCErrorDetailTypeValue
    sdp_line_number: int | None = None
    sctp_cause_code: int | None = None
    received_alert: int | None = None
    sent_alert: int | None = None
    http_request_status_code: int | None = None

    def __post_init__(self) -> None:
        self.error_detail = RTCErrorDetailType(self.error_detail)

    #: Alias for :attr:`error_detail`
    errorDetail: ClassVar[Alias[RTCErrorDetailType | RTCErrorDetailTypeValue]] = alias('error_detail')
    #: Alias for :attr:`sdp_line_number`
    sdpLineNumber: ClassVar[Alias[int | None]] = alias('sdp_line_number')
    #: Alias for :attr:`sctp_cause_code`
    sctpCauseCode: ClassVar[Alias[int | None]] = alias('sctp_cause_code')
    #: Alias for :attr:`received_alert`
    receivedAlert: ClassVar[Alias[int | None]] = alias('received_alert')
    #: Alias for :attr:`sent_alert`
    sentAlert: ClassVar[Alias[int | None]] = alias('sent_alert')
    #: Alias for :attr:`http_request_status_code`
    httpRequestStatusCode: ClassVar[Alias[int | None]] = alias('http_request_status_code')


class RTCError(OperationError):
    """An :obj:`OperationError` with WebRTC-specific members, copied from its :obj:`RTCErrorInit`.

    It's raised for errors of the native WebRTC engine that carry a detail, like a description that doesn't parse.
    The ``error`` events of data channels and transports carry it too.

    See :mdn:`RTCError`.

    Args:
        init (:obj:`RTCErrorInit`): The WebRTC-specific members.
        message (:obj:`str`, optional): The description of the error.

    Attributes:
        error_detail (:obj:`webrtc.RTCErrorDetailType`): The cause of the error. See :mdn:`RTCError/errorDetail`.
        sdp_line_number (:obj:`int`, optional): The line of the SDP that doesn't parse.
            See :mdn:`RTCError/sdpLineNumber`.
        sctp_cause_code (:obj:`int`, optional): The SCTP cause code of a failed data channel or association.
            See :mdn:`RTCError/sctpCauseCode`.
        received_alert (:obj:`int`, optional): The DTLS alert received from the remote peer.
            See :mdn:`RTCError/receivedAlert`.
        sent_alert (:obj:`int`, optional): The DTLS alert sent to the remote peer. See :mdn:`RTCError/sentAlert`.
        http_request_status_code (:obj:`int`, optional): The HTTP status code of a failed request.
    """

    def __init__(self, init: RTCErrorInit, message: str = '') -> None:
        super().__init__(message)
        self.error_detail = RTCErrorDetailType(init.error_detail)
        self.sdp_line_number = init.sdp_line_number
        self.sctp_cause_code = init.sctp_cause_code
        self.received_alert = init.received_alert
        self.sent_alert = init.sent_alert
        self.http_request_status_code = init.http_request_status_code

    #: Alias for :attr:`error_detail`
    errorDetail: ClassVar[Alias[RTCErrorDetailType]] = alias('error_detail')
    #: Alias for :attr:`sdp_line_number`
    sdpLineNumber: ClassVar[Alias[int | None]] = alias('sdp_line_number')
    #: Alias for :attr:`sctp_cause_code`
    sctpCauseCode: ClassVar[Alias[int | None]] = alias('sctp_cause_code')
    #: Alias for :attr:`received_alert`
    receivedAlert: ClassVar[Alias[int | None]] = alias('received_alert')
    #: Alias for :attr:`sent_alert`
    sentAlert: ClassVar[Alias[int | None]] = alias('sent_alert')
    #: Alias for :attr:`http_request_status_code`
    httpRequestStatusCode: ClassVar[Alias[int | None]] = alias('http_request_status_code')


_BY_RTC_ERROR_TYPE = {
    # the same mapping as Chromium's
    'UNSUPPORTED_OPERATION': OperationError,
    'UNSUPPORTED_PARAMETER': InvalidAccessError,
    'INVALID_PARAMETER': InvalidAccessError,
    'INVALID_RANGE': InvalidRangeError,
    'SYNTAX_ERROR': InvalidSyntaxError,
    'INVALID_STATE': InvalidStateError,
    'INVALID_MODIFICATION': InvalidModificationError,
    'NETWORK_ERROR': NetworkError,
    'RESOURCE_EXHAUSTED': OperationError,
    'INTERNAL_ERROR': OperationError,
}


def _from_native(
    error_type: str,
    message: str,
    *,
    detail: RTCErrorDetailType | None,
    sctp_cause_code: int | None,
    sdp_line_number: int | None,
) -> RTCException:
    """Creates the exception for a webrtc::RTCError, called from cpp/src/exceptions.cpp."""
    if error_type == 'OPERATION_ERROR_WITH_DATA' or detail is not None:
        init = RTCErrorInit(
            detail if detail is not None else RTCErrorDetailType.data_channel_failure,
            sctp_cause_code=sctp_cause_code,
            sdp_line_number=sdp_line_number,
        )
        return RTCError(init, message)
    return _BY_RTC_ERROR_TYPE.get(error_type, OperationError)(message)


def _event_error(native: wrtc.RTCCallbackException) -> RTCError:
    """The error of an ``error`` event. Channels and transports fail with errors that carry a detail."""
    error = native.toPython()
    if not isinstance(error, RTCError):
        msg = f'an error event carries an RTCError, not {type(error).__name__}'
        raise TypeError(msg)
    return error
