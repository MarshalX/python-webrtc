#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Exceptions raised by WebRTC operations, named after the ``DOMException`` of the specification."""

from typing import Optional

from webrtc import RTCErrorDetailType, wrtc
from webrtc.utils.names import alias

PythonWebRTCExceptionBase = wrtc.PythonWebRTCExceptionBase
PythonWebRTCException = wrtc.PythonWebRTCException
SdpParseException = wrtc.SdpParseException


class RTCException(PythonWebRTCException):
    """Base class of the errors reported by libwebrtc."""


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


class InvalidSyntaxError(RTCException, ValueError):
    """A string couldn't be parsed, like an ICE server URL. ``SyntaxError`` in the specification."""


class InvalidRangeError(RTCException, ValueError):
    """A value is out of the allowed range. ``RangeError`` in the specification."""


class InvalidCharacterError(RTCException, ValueError):
    """A string has a character that isn't allowed, like a DTMF tone that doesn't exist."""


class RTCError(OperationError):
    """An error carrying WebRTC-specific information.

    Args:
        error_detail (:obj:`RTCErrorDetailType`): The WebRTC-specific error code.
        message (:obj:`str`, optional): A description of the error.
        sdp_line_number (:obj:`int`, optional): The line of the SDP where a syntax error occurred.
        sctp_cause_code (:obj:`int`, optional): The SCTP cause code of a failed SCTP negotiation.
        received_alert (:obj:`int`, optional): The DTLS alert received from the remote peer.
        sent_alert (:obj:`int`, optional): The DTLS alert sent to the remote peer.
        http_request_status_code (:obj:`int`, optional): The HTTP status code of a failed request.

    Raises:
        :obj:`ValueError`: If ``error_detail`` isn't a member of :obj:`RTCErrorDetailType`.
    """

    def __init__(
        self,
        error_detail: RTCErrorDetailType,
        message: str = '',
        *,
        sdp_line_number: Optional[int] = None,
        sctp_cause_code: Optional[int] = None,
        received_alert: Optional[int] = None,
        sent_alert: Optional[int] = None,
        http_request_status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.error_detail = RTCErrorDetailType(error_detail)
        self.message = message
        self.sdp_line_number = sdp_line_number
        self.sctp_cause_code = sctp_cause_code
        self.received_alert = received_alert
        self.sent_alert = sent_alert
        self.http_request_status_code = http_request_status_code

    #: Alias for :attr:`error_detail`
    errorDetail = alias('error_detail')
    #: Alias for :attr:`sdp_line_number`
    sdpLineNumber = alias('sdp_line_number')
    #: Alias for :attr:`sctp_cause_code`
    sctpCauseCode = alias('sctp_cause_code')
    #: Alias for :attr:`received_alert`
    receivedAlert = alias('received_alert')
    #: Alias for :attr:`sent_alert`
    sentAlert = alias('sent_alert')
    #: Alias for :attr:`http_request_status_code`
    httpRequestStatusCode = alias('http_request_status_code')


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
    detail: Optional[RTCErrorDetailType],
    sctp_cause_code: Optional[int],
    sdp_line_number: Optional[int] = None,
) -> RTCException:
    """Creates the exception for a webrtc::RTCError. Called by name, with positional arguments, from
    cpp/src/exceptions.cpp."""
    if error_type == 'OPERATION_ERROR_WITH_DATA' or detail is not None:
        return RTCError(
            detail or RTCErrorDetailType.data_channel_failure,
            message,
            sctp_cause_code=sctp_cause_code,
            sdp_line_number=sdp_line_number,
        )
    return _BY_RTC_ERROR_TYPE.get(error_type, OperationError)(message)
