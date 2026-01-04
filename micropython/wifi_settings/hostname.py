#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Hostname for wifi-settings. The hostname can be specified in
# the WiFi settings file as "name=<xxx>".
#



from . import storage

import struct
import machine
try:
    # board id is decoded as a 64-bit big-endian unsigned integer
    # then re-encoded as 16 upper-case hex bytes. This never changes.
    BOARD_ID = "{:016X}".format(struct.unpack(">Q", machine.unique_id())[0])
except Exception:
    BOARD_ID = "0" * 16

# The hostname can be changed at runtime.
g_hostname = ""

def get_board_id_hex() -> str:
    """Return the unique board ID as 16 upper-case hex bytes."""
    return BOARD_ID

def get_hostname() -> str:
    """Return the hostname - either configured in the wifi settings file,
    or based on the unique board ID."""
    return g_hostname

def set_hostname() -> None:
    global g_hostname
    name = storage.get_value_for_key("name")
    if name:
        g_hostname = name
    else:
        # host name fallback: PicoW-<board id>
        g_hostname = "PicoW-" + get_board_id_hex()
