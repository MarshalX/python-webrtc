#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""WebIDL string conversions."""

from __future__ import annotations


def usv_string(value: str) -> str:
    """Converts to a USVString: lone surrogates become U+FFFD."""
    try:
        _ = value.encode()
    except UnicodeEncodeError:
        return value.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace')
    return value
