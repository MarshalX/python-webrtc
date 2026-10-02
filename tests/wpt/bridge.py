#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Python side of the WPT shim: does what shim.js asks on `webrtc` objects.

It returns {'ok': value} or {'error': {...}}, so exceptions reach JS with their type.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import inspect
import sys
import time
from typing import TYPE_CHECKING, Callable, TypeVar, Union

import pythonmonkey as pm

import webrtc
import webrtc.enums
from tests.wpt.loader import WPT_ROOT

if TYPE_CHECKING:
    from collections.abc import Awaitable, Coroutine

    from _typeshed import DataclassInstance


_T = TypeVar('_T')

Result = dict[str, object]
Buffer = Union[bytes, bytearray, memoryview]

# The loop of the test, set by the runner: code called from JS may not see it as the running loop
LOOP: asyncio.AbstractEventLoop | None = None

# what the shim turns into JS errors of their type, anything else reaches JS as a plain Error
BRIDGED_ERRORS = (TypeError, ValueError, OverflowError, webrtc.PythonWebRTCExceptionBase)

# Python objects without a native object, exposed to JS as interfaces
_PLAIN_INTERFACES = (
    webrtc.RTCIceCandidate,
    webrtc.VideoFrame,
    webrtc.AudioData,
    webrtc.ReadableStream,
    webrtc.ReadableStreamDefaultReader,
    webrtc.WritableStream,
    webrtc.WritableStreamDefaultWriter,
    webrtc.VideoTrackGenerator,
    webrtc.VideoColorSpace,
    webrtc.RTCRtpScriptTransformer,
    webrtc.RTCEncodedVideoFrame,
    webrtc.RTCEncodedAudioFrame,
)


# WebIDL names that aren't the camelCase of the snake_case ones
_IDL_NAMES = {'key_id': 'keyID'}


def _camel_case(name: str) -> str:
    if name in _IDL_NAMES:
        return _IDL_NAMES[name]
    first, *rest = name.split('_')
    return first + ''.join(part.title() for part in rest)


def _event_to_js(event: webrtc.Event) -> dict[str, object]:
    init = {_camel_case(k): to_js(v) for k, v in vars(event).items() if k not in {'type', 'target'}}
    return {'__event': type(event).__name__, 'type': event.type, 'init': init}


def _dictionary_to_js(value: DataclassInstance) -> dict[str, object]:
    # a dictionary in WebIDL, where missing members are left out
    members = ((f.name, getattr(value, f.name)) for f in dataclasses.fields(value))
    return {_camel_case(name): to_js(member) for name, member in members if member is not None}


def _enum_to_js(value: enum.Enum) -> object:
    # the values of the enums are the WebIDL ones
    return value.value


def _rect_to_js(value: webrtc.DOMRectReadOnly) -> object:
    return {'__rect': [value.x, value.y, value.width, value.height]}


def _blob_to_js(value: webrtc.Blob) -> object:
    return {'__blob': bytearray(bytes(value)), 'type': value.type}


def _description_to_js(value: webrtc.RTCSessionDescriptionInit) -> object:
    # a dictionary in WebIDL, but a WebRTCObject (it holds a native one) here, not a dataclass
    return value.to_json()


def _wrapper_to_js(value: webrtc.WebRTCObject[object]) -> object:
    # Wrappers are created per access, but they hash as the native object they share, which identifies it
    return {'__type': type(value).__name__, '__id': hash(value), '__obj': value}


def _plain_to_js(value: object) -> object:
    return {'__type': type(value).__name__, '__id': id(value), '__obj': value}


def _error_to_js(value: BaseException) -> object:
    return {'__error': _error(value)['error']}


def _one_stats_to_js(stats: webrtc.RTCStats) -> object:
    members = _dictionary_to_js(stats)
    # address is nullable: null when the address isn't exposed
    if isinstance(stats, webrtc.RTCIceCandidateStats):
        members['address'] = stats.address
    return members


def _stats_to_js(value: webrtc.RTCStatsReport) -> object:
    return {'__statsReport': [[stats_id, _one_stats_to_js(stats)] for stats_id, stats in value.items()]}


def _bytes_to_js(value: bytes) -> object:
    # PythonMonkey shares a bytearray as a Uint8Array, the shim copies it
    return {'__bytes': bytearray(value)}


def _dict_to_js(value: dict[object, object]) -> object:
    return {k: to_js(v) for k, v in value.items()}


def _sequence_to_js(value: list[object] | tuple[object, ...]) -> object:
    return [to_js(v) for v in value]


# in order: the first type that matches converts the value
_CONVERTERS: list[tuple[type | tuple[type, ...], Callable[..., object]]] = [
    (enum.Enum, _enum_to_js),
    (webrtc.DOMRectReadOnly, _rect_to_js),
    (webrtc.Blob, _blob_to_js),
    (webrtc.RTCSessionDescriptionInit, _description_to_js),
    (webrtc.WebRTCObject, _wrapper_to_js),
    (_PLAIN_INTERFACES, _plain_to_js),
    (BaseException, _error_to_js),
    (webrtc.RTCStatsReport, _stats_to_js),
    (bytes, _bytes_to_js),
    (webrtc.Event, _event_to_js),
    (dict, _dict_to_js),
    ((list, tuple), _sequence_to_js),
]


def to_js(value: object) -> object:
    """A Python value as the shim reads it."""
    for types, convert in _CONVERTERS:
        if isinstance(value, types):
            return convert(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _dictionary_to_js(value)
    return value


def _to_enum(value: dict[str, object]) -> object:
    # named after its webrtc counterpart, whose values are the WebIDL ones
    enum_cls = getattr(webrtc.enums, str(value['__enum']))
    try:
        return enum_cls(value['value'])
    except ValueError:
        if bool(value.get('strict', True)):
            msg = f"'{value['value']}' is not a valid value for enumeration {value['__enum']}"
            raise TypeError(msg) from None
        # A DOMString in WebIDL rather than an enum, so it's up to the library to reject it
        return value['value']


def _object_from_js(value: list[object] | memoryview | dict[str, object]) -> object:
    if isinstance(value, list):
        return [from_js(v) for v in value]
    if isinstance(value, memoryview):
        # an ArrayBuffer or a view of one
        return bytes(value)
    return _dict_from_js(value)


def _dict_from_js(value: dict[str, object]) -> object:
    if '__enum' in value:
        return _to_enum(value)
    if '__model' in value:
        # a WebIDL dictionary the library has a keyword model for
        return getattr(webrtc, str(value['__model']))(**from_js(value['kwargs']))
    if '__json' in value:
        # a WebIDL dictionary as JS has it, which the library converts with its from_json
        return getattr(webrtc, str(value['__json'])).from_json(from_js(value['value']))
    return {k: from_js(v) for k, v in value.items()}


def from_js(value: object) -> object:
    """A value from the shim as Python takes it."""
    if value is pm.null:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (list, memoryview, dict)):
        return _object_from_js(value)
    return value


def _error(exc: BaseException) -> Result:
    # the most specific class known to the shim
    kind = next(
        (cls.__name__ for cls in type(exc).__mro__ if cls.__module__ in {'webrtc.exceptions', 'wrtc', 'builtins'}),
        'Error',
    )
    error: dict[str, object] = {'kind': kind, 'message': str(exc)}
    if isinstance(exc, webrtc.OverconstrainedError):
        error['constraint'] = exc.constraint
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


def _guard(func: Callable[[], object]) -> Result:
    try:
        return {'ok': to_js(func())}
    except BRIDGED_ERRORS as e:
        return _error(e)


async def _guard_async(awaitable: Callable[[], Awaitable[object]]) -> Result:
    try:
        return {'ok': to_js(await awaitable())}
    except BRIDGED_ERRORS as e:
        return _error(e)


def _start(coroutine: Coroutine[object, object, Result]) -> asyncio.Future[Result]:
    # Started eagerly so the synchronous steps of the method run when it's called, not on the next iteration of
    # the loop. Before Python 3.12 they run one iteration later, so results that depend on event order may differ.
    if sys.version_info >= (3, 12):
        return asyncio.Task(coroutine, loop=LOOP, eager_start=True)
    return asyncio.ensure_future(coroutine, loop=LOOP)


def get_attr(obj: object, name: str) -> Result:
    return _guard(lambda: getattr(obj, name))


def set_attr(obj: object, name: str, value: object) -> Result:
    return _guard(lambda: setattr(obj, name, from_js(value)))


def _from_js_as(kind: type[_T], value: object) -> _T:
    """A value from the shim that converts to a type, like a dictionary the library has a model of."""
    result = from_js(value)
    if not isinstance(result, kind):
        msg = f'expected {kind.__name__} from JS, got {type(result).__name__}'
        raise TypeError(msg)
    return result


def _call(obj: object, name: str, arguments: dict[str, object]) -> object:
    """Calls a method with {'args': [...], 'kwargs': {...}} from JS."""
    args, kwargs = arguments['args'], arguments.get('kwargs')
    if not isinstance(args, list):
        msg = f'args from JS is not an array: {args!r}'
        raise TypeError(msg)
    if kwargs is not None and not isinstance(kwargs, dict):
        msg = f'kwargs from JS is not an object: {kwargs!r}'
        raise TypeError(msg)
    keywords: dict[object, object] = dict(kwargs) if kwargs is not None else {}
    return getattr(obj, name)(*from_js(list(args)), **from_js(keywords))


def _awaitable(value: object) -> Awaitable[object]:
    if not inspect.isawaitable(value):
        msg = f'{type(value).__name__} is not awaitable'
        raise TypeError(msg)
    return value


def call_method(obj: object, name: str, arguments: dict[str, object]) -> Result:
    return _guard(lambda: _call(obj, name, arguments))


def call_async_method(obj: object, name: str, arguments: dict[str, object]) -> asyncio.Future[Result]:
    return _start(_guard_async(lambda: _awaitable(_call(obj, name, arguments))))


def await_attr(obj: object, name: str) -> asyncio.Future[Result]:
    """An attribute that is a future (like the closed promise of a reader), awaited."""

    async def attr() -> object:
        return await getattr(obj, name)

    return asyncio.ensure_future(_guard_async(attr), loop=LOOP)


def video_frame_copy_to(frame: webrtc.VideoFrame, destination: Buffer, options: object) -> asyncio.Future[Result]:
    """Copies a frame into the bytes of a JS buffer, which the shim writes back."""

    async def copy() -> dict[str, object]:
        data = bytearray(destination)
        layout = await frame.copy_to(data, _from_js_as(webrtc.VideoFrameCopyToOptions, options))
        return {'layout': layout, 'data': bytes(data)}

    return _start(_guard_async(copy))


def audio_data_copy_to(audio: webrtc.AudioData, destination: Buffer, options: object) -> Result:
    """Copies samples into the bytes of a JS buffer, which the shim writes back."""

    def copy() -> bytes:
        data = bytearray(destination)
        audio.copy_to(data, _from_js_as(webrtc.AudioDataCopyToOptions, options))
        return bytes(data)

    return _guard(copy)


def construct(name: str, kwargs: dict[str, object], args: list[object] | None = None) -> Result:
    return _guard(
        lambda: getattr(webrtc, name)(*from_js(list(args) if args is not None else []), **from_js(dict(kwargs)))
    )


def get_user_media(constraints: object) -> asyncio.Future[Result]:
    # the shim converts the constraints as WebIDL does, the library validates them
    return call_async_method(webrtc.media_devices, 'get_user_media', {'args': [constraints]})


def call_static(class_name: str, name: str, args: list[object]) -> Result:
    return _guard(lambda: getattr(getattr(webrtc, class_name), name)(*from_js(list(args))))


def call_async_static(class_name: str, name: str, args: list[object]) -> asyncio.Future[Result]:
    return call_async_method(getattr(webrtc, class_name), name, {'args': args})


def now() -> float:
    """Milliseconds since the epoch, with the precision of the clock of libwebrtc stats."""
    return time.time() * 1000


def subscribe(obj: webrtc.EventTarget, name: str, callback: Callable[[object], object]) -> Result:
    """Delivers the events of a type to a JS callback, which dispatches them to the JS listeners."""

    def deliver(event: webrtc.Event) -> None:
        callback(to_js(event))

    def add_listener() -> None:
        # nothing to return to JS: on() returns the handler
        obj.on(name, deliver)

    return _guard(add_listener)


def wrap(value: object) -> Result:
    """A Python object JS got as it is (like the event a JS callback is called with), as the shim reads it."""
    return _guard(lambda: value)


def get_buffer(obj: object, name: str) -> Result:
    """A bytearray attribute as [identity, bytearray, detached]: JS shares its memory, one ArrayBuffer for each."""

    def get() -> list[object]:
        value = getattr(obj, name)
        # the data of an encoded frame written to its transformer, an ArrayBuffer transferred in a browser
        detached = bool(getattr(obj, '_detached', False))
        return [id(value), value, detached]

    return _guard(get)


def read_text(path: str) -> Result:
    """A file of the WPT checkout by its path from the root, like the script of a Worker."""
    return _guard((WPT_ROOT / path.lstrip('/')).read_text)


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
        await_attr,
        video_frame_copy_to,
        audio_data_copy_to,
        get_user_media,
        now,
        subscribe,
        wrap,
        get_buffer,
        read_text,
    )
}
