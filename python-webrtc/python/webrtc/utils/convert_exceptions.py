#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

__CALLBACK_EXCEPTION_TO_EXCEPTION = None


def __init_callback_exception_to_exception_dict():
    global __CALLBACK_EXCEPTION_TO_EXCEPTION

    import wrtc
    import webrtc

    __CALLBACK_EXCEPTION_TO_EXCEPTION = {
        wrtc.CallbackPythonWebRTCException: webrtc.PythonWebRTCException,
        wrtc.RTCCallbackException: webrtc.RTCException,
    }


def convert_from_callback_exception_to_exception(callback_exception):
    if not __CALLBACK_EXCEPTION_TO_EXCEPTION:
        __init_callback_exception_to_exception_dict()

    cls = __CALLBACK_EXCEPTION_TO_EXCEPTION[type(callback_exception)]
    return cls(callback_exception.what())
