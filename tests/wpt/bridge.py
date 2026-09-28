#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Python side of the WPT shim.

It knows nothing about WebRTC interfaces: shim.js decides what to read, write and call, and this module does it
on `webrtc` objects. Every call returns {'ok': value} or {'error': {...}}, so that exceptions reach JS with their
Python type and error code instead of as a generic Error.
"""

import asyncio
import dataclasses
import sys
import time

import pythonmonkey as pm

import webrtc

# WebIDL enums the shim converts, by the name of their webrtc counterpart
# The loop of the test, set by the runner: code called from JS may not see it as the running loop
LOOP = None

_ENUMS = {
    'MediaType': webrtc.MediaType,
    'TransceiverDirection': webrtc.TransceiverDirection,
    'RTCSdpType': webrtc.RTCSdpType,
    'RTCIceTransportPolicy': webrtc.RTCIceTransportPolicy,
    'RTCIceRole': webrtc.RTCIceRole,
    'RTCBundlePolicy': webrtc.RTCBundlePolicy,
    'RTCRtcpMuxPolicy': webrtc.RTCRtcpMuxPolicy,
    'RTCRtpHeaderEncryptionPolicy': webrtc.RTCRtpHeaderEncryptionPolicy,
    'RTCPriorityType': webrtc.RTCPriorityType,
    'RTCDegradationPreference': webrtc.RTCDegradationPreference,
    'RTCErrorDetailType': webrtc.RTCErrorDetailType,
}


def _is_enum(value):
    return hasattr(type(value), '__members__') and hasattr(value, 'name')


# Python objects without a native object, exposed to JS as interfaces
_PLAIN_INTERFACES = (webrtc.RTCIceCandidate,)


def _camel_case(name):
    first, *rest = name.split('_')
    return first + ''.join(part.title() for part in rest)


def to_js(value):
    if isinstance(value, webrtc.RTCDtlsFingerprint):
        # a dictionary in WebIDL
        return {'algorithm': value.algorithm, 'value': value.value}
    if isinstance(value, webrtc.RTCSessionDescriptionInit):
        # a dictionary in WebIDL
        return {'type': to_js(value.type), 'sdp': value.sdp}
    if isinstance(value, webrtc.WebRTCObject):
        # Wrappers are created per access, but the native object is shared, so its id identifies the WebRTC object
        return {'__type': type(value).__name__, '__id': id(value._native_obj), '__obj': value}
    if isinstance(value, _PLAIN_INTERFACES):
        return {'__type': type(value).__name__, '__id': id(value), '__obj': value}
    if isinstance(value, BaseException):
        return {'__error': _error(value)['error']}
    if isinstance(value, webrtc.RTCStatsReport):
        return {'__statsReport': [[stats_id, dict(stats)] for stats_id, stats in value.items()]}
    if isinstance(value, bytes):
        # PythonMonkey shares a bytearray as a Uint8Array, the shim copies it
        return {'__bytes': bytearray(value)}
    if isinstance(value, webrtc.Event):
        init = {_camel_case(k): to_js(v) for k, v in vars(value).items() if k not in ('type', 'target')}
        return {'__event': type(value).__name__, 'type': value.type, 'init': init}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # a dictionary in WebIDL, where missing members are left out
        return {
            _camel_case(f.name): to_js(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if getattr(value, f.name) is not None
        }
    if isinstance(value, dict):
        return {k: to_js(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_js(v) for v in value]
    if _is_enum(value):
        return {'__enum': value.name}
    return value


def _to_enum(value):
    enum_cls = _ENUMS[value['__enum']]
    member = getattr(enum_cls, str(value['value']).replace('-', '_'), None)
    if isinstance(member, enum_cls):
        return member
    if value.get('strict', True):
        raise TypeError(f"'{value['value']}' is not a valid value for enumeration {value['__enum']}")
    # A DOMString in WebIDL rather than an enum, so it's up to the library to reject it
    return value['value']


def from_js(value):
    if value is pm.null:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [from_js(v) for v in value]
    if isinstance(value, memoryview):
        # an ArrayBuffer or a view of one
        return bytes(value)
    if isinstance(value, dict):
        if '__enum' in value:
            return _to_enum(value)
        if '__model' in value:
            # a WebIDL dictionary the library has a keyword model for
            return getattr(webrtc, value['__model'])(**from_js(value['kwargs']))
        return {k: from_js(v) for k, v in value.items()}
    return value


def _error(exc):
    # the most specific class known to the shim
    for cls in type(exc).__mro__:
        if cls.__module__ in ('webrtc.exceptions', 'wrtc', 'builtins'):
            kind = cls.__name__
            break
    error = {'kind': kind, 'message': str(exc)}
    if isinstance(exc, webrtc.RTCError):
        error['init'] = {
            'errorDetail': exc.error_detail.value,
            'sdpLineNumber': exc.sdp_line_number,
            'sctpCauseCode': exc.sctp_cause_code,
            'receivedAlert': exc.received_alert,
            'sentAlert': exc.sent_alert,
            'httpRequestStatusCode': exc.http_request_status_code,
        }
    return {'error': error}


def _guard(func):
    try:
        return {'ok': to_js(func())}
    except Exception as e:
        return _error(e)


def get_attr(obj, name):
    return _guard(lambda: getattr(obj, name))


def set_attr(obj, name, value):
    return _guard(lambda: setattr(obj, name, from_js(value)))


def call_method(obj, name, args, kwargs=None):
    return _guard(lambda: getattr(obj, name)(*from_js(list(args)), **from_js(dict(kwargs or {}))))


async def _call_async_method(obj, name, args, kwargs):
    try:
        return {'ok': to_js(await getattr(obj, name)(*from_js(list(args)), **from_js(dict(kwargs or {}))))}
    except Exception as e:
        return _error(e)


def call_async_method(obj, name, args, kwargs=None):
    # Started right away, as a browser runs the synchronous steps of a method when it's called: a coroutine
    # would otherwise only start on the next iteration of the loop
    coroutine = _call_async_method(obj, name, args, kwargs)
    if sys.version_info >= (3, 12):
        return asyncio.Task(coroutine, loop=LOOP, eager_start=True)
    return asyncio.ensure_future(coroutine, loop=LOOP)


def _construct(name, kwargs):
    kwargs = from_js(dict(kwargs))
    if name == 'RTCSessionDescription':
        init = webrtc.RTCSessionDescriptionInit(kwargs['type'], kwargs.get('sdp', ''))
        return webrtc.RTCSessionDescription(init)
    if name == 'RtpTransceiverInit':
        kwargs['send_encodings'] = [webrtc.RtpEncodingParameters(**e) for e in kwargs.get('send_encodings') or []]
    return getattr(webrtc, name)(**kwargs)


def construct(name, kwargs):
    return _guard(lambda: _construct(name, kwargs))


def get_user_media(kwargs):
    return _guard(lambda: webrtc.get_user_media(**from_js(dict(kwargs))))


def call_static(class_name, name, args):
    return _guard(lambda: getattr(getattr(webrtc, class_name), name)(*from_js(list(args))))


def call_async_static(class_name, name, args):
    return call_async_method(getattr(webrtc, class_name), name, args)


def now():
    """Milliseconds since the epoch, with the precision of the clock of libwebrtc stats"""
    return time.time() * 1000


def subscribe(obj, name, callback):
    """Delivers the events of a type to a JS callback, which dispatches them to the JS listeners"""
    return _guard(lambda: obj.on(name, lambda event: callback(to_js(event))) and None)


EXPORTS = {
    f.__name__: f
    for f in (
        get_attr,
        set_attr,
        call_method,
        call_async_method,
        call_static,
        call_async_static,
        construct,
        get_user_media,
        now,
        subscribe,
    )
}
