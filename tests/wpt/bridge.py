#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Python side of the WPT shim: does what shim.js asks on `webrtc` objects, returning {'ok': value} or
{'error': {...}} so exceptions reach JS with their type."""

import asyncio
import dataclasses
import enum
import sys
import time

import pythonmonkey as pm

import webrtc
import webrtc.enums

# The loop of the test, set by the runner: code called from JS may not see it as the running loop
LOOP = None

# Python objects without a native object, exposed to JS as interfaces
_PLAIN_INTERFACES = (webrtc.RTCIceCandidate,)


def _camel_case(name):
    first, *rest = name.split('_')
    return first + ''.join(part.title() for part in rest)


def to_js(value):
    if isinstance(value, enum.Enum):
        # the values of the enums are the WebIDL ones
        return value.value
    if isinstance(value, webrtc.RTCSessionDescriptionInit):
        # a dictionary in WebIDL, but a WebRTCObject (it holds a native one) here, not a dataclass
        return value.to_json()
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
    return value


def _to_enum(value):
    # named after its webrtc counterpart, whose values are the WebIDL ones
    enum_cls = getattr(webrtc.enums, value['__enum'])
    try:
        return enum_cls(value['value'])
    except ValueError:
        if value.get('strict', True):
            raise TypeError(f"'{value['value']}' is not a valid value for enumeration {value['__enum']}") from None
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
    else:
        kind = 'Error'
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


def _call(obj, name, args, kwargs):
    return getattr(obj, name)(*from_js(list(args)), **from_js(dict(kwargs or {})))


def call_method(obj, name, args, kwargs=None):
    return _guard(lambda: _call(obj, name, args, kwargs))


async def _call_async_method(obj, name, args, kwargs):
    try:
        return {'ok': to_js(await _call(obj, name, args, kwargs))}
    except Exception as e:
        return _error(e)


def call_async_method(obj, name, args, kwargs=None):
    # Started eagerly so the synchronous steps of the method run when it's called, not on the next iteration of
    # the loop. Before Python 3.12 they run one iteration later, so results that depend on event order may differ.
    coroutine = _call_async_method(obj, name, args, kwargs)
    if sys.version_info >= (3, 12):
        return asyncio.Task(coroutine, loop=LOOP, eager_start=True)
    return asyncio.ensure_future(coroutine, loop=LOOP)


def construct(name, kwargs):
    return _guard(lambda: getattr(webrtc, name)(**from_js(dict(kwargs))))


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

    def deliver(event):
        callback(to_js(event))

    def add_listener():
        # nothing to return to JS: on() returns the handler
        obj.on(name, deliver)

    return _guard(add_listener)


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
