#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The driver of aiortc: ``python -m benchmarks.drivers.aiortc`` with the interpreter of its own environment.

aiortc gathers every candidate in ``setLocalDescription``, so its descriptions always carry them: it doesn't trickle.
"""
