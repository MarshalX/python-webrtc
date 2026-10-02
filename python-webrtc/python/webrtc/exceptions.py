#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Exceptions raised by WebRTC operations, named after the ``DOMException`` of the specification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from webrtc import RTCErrorDetailType, wrtc
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.enums import RTCErrorDetailTypeValue

PythonWebRTCExceptionBase = wrtc.PythonWebRTCExceptionBase
PythonWebRTCException = wrtc.PythonWebRTCException
SdpParseException = wrtc.SdpParseException


class RTCException(PythonWebRTCException):
    """Base class of the errors reported by libwebrtc, the ``DOMException`` of the specification."""

    @property
    def message(self) -> str:
        """:obj:`str`: A description of the error."""
        return str(self.args[0]) if len(self.args) > 0 else ''


class InvalidStateError(RTCException):
    """The object is in a state that doesn't allow the operation, like a closed connection."""


class InvalidAccessError(RTCException):
    """A parameter or an operation isn't supported by the object, like an invalid description."""


class InvalidModificationError(RTCException):
    """An attempt to modify something that can't be modified, like a read-only parameter."""


class OperationError(RTCException):
    """The operation failed for an operation-specific reason."""


class NotSupportedError(RTCException):
    """The operation or a value isn't supported by the implementation."""


class NetworkError(RTCException):
    """An error of an underlying network protocol."""


class NotFoundError(RTCException):
    """An object isn't found, like a simulcast layer of an unknown ``rid``."""


class NotAllowedError(RTCException):
    """The operation isn't allowed, like with a malformed ``rid``."""


class DataCloneError(RTCException):
    """An object can't be transferred, like a buffer listed twice in ``transfer``."""


class InvalidSyntaxError(RTCException, ValueError):
    """A string couldn't be parsed, like an ICE server URL. ``SyntaxError`` in the specification."""


class InvalidRangeError(RTCException, ValueError):
    """A value is out of the allowed range. ``RangeError`` in the specification."""


class InvalidCharacterError(RTCException, ValueError):
    """A string has a character that isn't allowed, like a DTMF tone that doesn't exist."""


class OverconstrainedError(RTCException):
    """A required constraint of a track can't be satisfied.

    Args:
        constraint (:obj:`str`): The constraint, like ``'width'``.
        message (:obj:`str`, optional): A description of the error.
    """

    def __init__(self, constraint: str, message: str = '') -> None:
        super().__init__(message if message != '' else f"The constraint {constraint} can't be satisfied")
        self.constraint = constraint


@dataclass
class RTCErrorInit(Dictionary):
    """The WebRTC-specific information of an :obj:`RTCError`.

    Args:
        error_detail (:obj:`webrtc.RTCErrorDetailType`): The WebRTC-specific error code.
        sdp_line_number (:obj:`int`, optional): The line of the SDP where a syntax error occurred.
        sctp_cause_code (:obj:`int`, optional): The SCTP cause code of a failed SCTP negotiation.
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
    """An error carrying WebRTC-specific information, the members of its :obj:`RTCErrorInit`.

    Args:
        init (:obj:`RTCErrorInit`): The WebRTC-specific information.
        message (:obj:`str`, optional): A description of the error.
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
    """The error of an ``error`` event: libwebrtc fails channels and transports with errors that carry a detail."""
    error = native.toPython()
    if not isinstance(error, RTCError):
        msg = f'an error event carries an RTCError, not {type(error).__name__}'
        raise TypeError(msg)
    return error
