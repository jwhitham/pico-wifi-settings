"""
Type shim module interface for pico-wifi-settings Python code.

The "typing" module doesn't exist in Micropython. This typing_shim
module provides compatibility for Micropython while still allowing
"typing" to be used with CPython.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

try:
    from typing import *
except ImportError:
    pass
