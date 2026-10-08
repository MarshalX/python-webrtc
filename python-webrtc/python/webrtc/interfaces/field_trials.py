#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Field trials, which turn on experimental features of the WebRTC engine before it starts."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, MutableMapping
from typing import TYPE_CHECKING, overload

from typing_extensions import override

import wrtc

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem

# what the engine accepted, shared by every FieldTrials
_trials: dict[str, str] = {}


def _validate(name: object, group: object) -> None:
    for kind, value in (('name', name), ('group', group)):
        if not isinstance(value, str):
            msg = f'a field trial {kind} must be a str, not {type(value).__name__}'
            raise TypeError(msg)
        if value == '' or '/' in value:
            msg = f"a field trial {kind} can't be empty or contain '/': {value!r}"
            raise ValueError(msg)


def _format(trials: dict[str, str]) -> str:
    return ''.join(f'{name}/{group}/' for name, group in trials.items())


def _parse(trials: str) -> dict[str, str]:
    *parts, rest = trials.split('/')
    if rest != '' or len(parts) % 2 != 0:
        msg = f"{trials!r} isn't a list of 'Name/Group/'"
        raise ValueError(msg)
    trials_by_name: dict[str, str] = {}
    for name, group in zip(parts[::2], parts[1::2]):
        _validate(name, group)
        if trials_by_name.setdefault(name, group) != group:
            msg = f'{name!r} has two groups in {trials!r}'
            raise ValueError(msg)
    return trials_by_name


def _apply(trials: dict[str, str]) -> None:
    wrtc._set_field_trials(_format(trials))
    _trials.clear()
    _trials.update(trials)


class FieldTrials(MutableMapping[str, str]):
    """The field trials of the engine: a mapping of trial names to groups, like ``{'WebRTC-Sctp-Snap': 'Enabled'}``.

    Browsers take them from a command-line flag. Here, set them in :data:`webrtc.field_trials`, or in the
    ``WRTC_FIELD_TRIALS`` environment variable in the flag's ``Name/Group/`` format, before the first
    :class:`webrtc.RTCPeerConnection` or :class:`webrtc.RTCIceTransport`. They're fixed from then on, for the life of
    the process: a change raises :obj:`webrtc.InvalidStateError`.

    ``str()`` gives the ``Name/Group/`` format. Unknown names are accepted, and do nothing.
    """

    @override
    def __getitem__(self, name: str) -> str:
        return _trials[name]

    @override
    def __setitem__(self, name: str, group: str) -> None:
        self.update({name: group})

    @override
    def __delitem__(self, name: str) -> None:
        trials = dict(_trials)
        del trials[name]
        _apply(trials)

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(_trials)

    @override
    def __len__(self) -> int:
        return len(_trials)

    @overload
    def update(self, other: SupportsKeysAndGetItem[str, str], /, **kwargs: str) -> None: ...

    @overload
    def update(self, other: Iterable[tuple[str, str]], /, **kwargs: str) -> None: ...

    @overload
    def update(self, /, **kwargs: str) -> None: ...

    @override
    def update(
        self, other: SupportsKeysAndGetItem[str, str] | Iterable[tuple[str, str]] = (), /, **kwargs: str
    ) -> None:
        """Sets several trials at once, or none of them if one is invalid."""
        new: dict[str, str] = dict(other)
        new.update(kwargs)
        for name, group in new.items():
            _validate(name, group)
        _apply(_trials | new)

    @override
    def clear(self) -> None:
        _apply({})

    @override
    def __str__(self) -> str:
        return _format(_trials)

    @override
    def __repr__(self) -> str:
        return f'FieldTrials({_trials!r})'


#: The field trials of the process. See :class:`webrtc.FieldTrials`.
field_trials = FieldTrials()
#: Alias for :data:`field_trials`
fieldTrials = field_trials

if (_environment := os.environ.get('WRTC_FIELD_TRIALS', '')) != '':
    try:
        _apply(_parse(_environment))
    except ValueError as e:
        msg = f'Invalid WRTC_FIELD_TRIALS: {e}'
        raise ValueError(msg) from None
