#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import wrtc


def convert_from_callback_exception_to_exception(callback_exception) -> Exception:
    if isinstance(callback_exception, wrtc.RTCCallbackException):
        return callback_exception.to_python()

    from webrtc import PythonWebRTCException

    return PythonWebRTCException(callback_exception.what())
