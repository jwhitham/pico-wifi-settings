"""
Remote access protocol library for pico-wifi-settings.

This library provides the implementation for the "remote_picotool" client.

Pico firmware built with the wifi-settings library, an 'update_secret'
and the -DWIFI_SETTINGS_REMOTE build option can be remotely controlled
and updated using this library.

See https://github.com/jwhitham/pico-wifi-settings

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""
from .exceptions import *
from .handler_ids import *
from .pico_info import Family, PicoInfo
from .file_type import get_file_type, FileType

try:
    import micropython as __testing_only__  # type: ignore
except ImportError:
    # Not Micropython
    from . import aio, remote_picotool
