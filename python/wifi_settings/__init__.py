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
from . import protocol, version, configuration, file_io_protocol

try:
    # For use on Micropython
    import micropython as __testing_only_1__  # type: ignore
    import machine as __testing_only_2__  # type: ignore
    from .upy.connection import has_no_wifi_details, get_connect_status_text, get_hw_status_text, get_ip_status_text
    from .upy.connection import get_ip, get_ssid, get_ssid_status, init, deinit, connect, disconnect, is_connected
    from .upy.remote import update_secret, set_handler, set_two_stage_handler
except ImportError:
    # For use on CPython
    from . import aio, remote_picotool
