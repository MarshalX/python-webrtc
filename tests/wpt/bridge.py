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

import re

import pythonmonkey as pm

import webrtc

_RTC_ERROR_CODE = re.compile(r'^\[([A-Z_]+)\]\s*')

# WebIDL enums the shim converts, by the name of their webrtc counterpart
_ENUMS = {
    'MediaType': webrtc.MediaType,
    'TransceiverDirection': webrtc.TransceiverDirection,
    'RTCSdpType': webrtc.RTCSdpType,
}


def _is_enum(value):
    return hasattr(type(value), '__members__') and hasattr(value, 'name')


def to_js(value):
    if isinstance(value, webrtc.WebRTCObject):
        # Wrappers are created per access, but the native object is shared, so its id identifies the WebRTC object
        return {'__type': type(value).__name__, '__id': id(value._native_obj), '__obj': value}
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
    if isinstance(value, dict):
        if '__enum' in value:
            return _to_enum(value)
        return {k: from_js(v) for k, v in value.items()}
    return value


def _error(exc):
    message = str(exc)
    code = None
    if isinstance(exc, webrtc.RTCException):
        kind = 'RTCException'
        match = _RTC_ERROR_CODE.match(message)
        if match:
            code = match.group(1)
            message = message[match.end() :]
    elif isinstance(exc, webrtc.PythonWebRTCException):
        kind = 'PythonWebRTCException'
    elif isinstance(exc, TypeError):
        kind = 'TypeError'
    else:
        kind = type(exc).__name__
    return {'error': {'kind': kind, 'code': code, 'message': message}}


def _guard(func):
    try:
        return {'ok': to_js(func())}
    except Exception as e:
        return _error(e)


def get_attr(obj, name):
    return _guard(lambda: getattr(obj, name))


def set_attr(obj, name, value):
    return _guard(lambda: setattr(obj, name, from_js(value)))


def call_method(obj, name, args):
    return _guard(lambda: getattr(obj, name)(*from_js(list(args))))


async def call_async_method(obj, name, args):
    try:
        return {'ok': to_js(await getattr(obj, name)(*from_js(list(args))))}
    except Exception as e:
        return _error(e)


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


def get_user_media():
    return _guard(webrtc.get_user_media)


EXPORTS = {f.__name__: f for f in (get_attr, set_attr, call_method, call_async_method, construct, get_user_media)}
