#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

import wrtc

from webrtc import MediaStream

if TYPE_CHECKING:
    import webrtc


# TODO constraints
def get_user_media(constraints=None) -> 'webrtc.MediaStream':
    """Method prompts the user for permission to use a media input which produces a :obj:`webrtc.MediaStream`
    with tracks containing the requested types of media.

    Returns:
        :obj:`webrtc.MediaStream`: A :obj:`webrtc.MediaStream` object representing the media stream.
    """
    return MediaStream._wrap(wrtc.getUserMedia())


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
