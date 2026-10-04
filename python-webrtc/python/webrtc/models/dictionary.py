#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The base class of the WebIDL dictionaries. Methods take them as typed dataclasses in place of plain dicts."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import fields
from typing import TYPE_CHECKING, ClassVar

from webrtc.utils.names import camel_case, members

if TYPE_CHECKING:
    from dataclasses import Field

    from typing_extensions import Self


class Dictionary:
    """The base class of the dataclasses of WebIDL dictionaries.

    Methods take these dataclasses in place of plain dicts. :meth:`from_json` and :meth:`to_json` convert them to and
    from the JSON form that is exchanged with the remote peer.
    """

    # members holding dictionaries, or lists of them, whose JSON forms from_json converts too
    _dictionaries: ClassVar[Mapping[str, type[Dictionary]]] = {}

    if TYPE_CHECKING:  # every subclass is a dataclass
        __dataclass_fields__: ClassVar[dict[str, Field[object]]]

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> Self:
        """Creates the dictionary from its JSON form, like one received from the remote peer.

        Keys can be the camelCase names of the specification or the snake_case ones. Unknown keys are ignored, and
        nested dictionaries are converted too.

        Args:
            value (:obj:`dict`): The JSON form.

        Returns:
            The dictionary.

        Raises:
            TypeError: If the value isn't a mapping, or a required member is missing.
        """
        if not isinstance(value, Mapping):
            msg = f'{cls.__name__} is created from a mapping, not {type(value).__name__}'
            raise TypeError(msg)
        kwargs = members(value, [field.name for field in fields(cls)])
        for name, dictionary in cls._dictionaries.items():
            if name in kwargs:
                kwargs[name] = dictionary._from_json_member(kwargs[name])
        return cls(**kwargs)

    def to_json(self) -> dict[str, object]:
        """Returns the JSON form of the dictionary, like one to send to the remote peer.

        Keys are the camelCase names of the specification. Members that are :obj:`None` are left out, enums become
        their values, and nested dictionaries are converted too.

        Returns:
            :obj:`dict`: The JSON form.
        """
        json: dict[str, object] = {}
        for field in fields(self):
            value: object = getattr(self, field.name)
            if value is not None:
                json[camel_case(field.name)] = _json_value(value)
        return json

    @classmethod
    def _from_json_member(cls, value: object) -> object:
        """A member that holds the dictionary, a list of them, or another type of a union, which stays as it is."""
        if isinstance(value, Mapping):
            return cls.from_json(value)
        if isinstance(value, list):
            return [cls.from_json(item) if isinstance(item, Mapping) else item for item in value]
        return value


def _json_value(value: object) -> object:
    if isinstance(value, Dictionary):
        return value.to_json()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        items: list[object] | tuple[object, ...] = value
        return [_json_value(item) for item in items]
    return value
