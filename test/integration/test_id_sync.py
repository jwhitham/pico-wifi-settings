#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Build tool for checking that C/C++ ID numbers match Python ID numbers.
#

import re
import typing
from pathlib import Path

import wifi_settings

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.parent.absolute()
RE_DEFINE = re.compile(r"^#define\s+([^\s]*)\s+(\d+).*$") 
RE_ENUM = re.compile(r"^\s*([^\s]*)\s*=\s*(\d+)\s*,.*$") 
C_ID_FILES = [
    PICO_WIFI_SETTINGS_ROOT_PATH / "include/wifi_settings/wifi_settings_connect.h",
    PICO_WIFI_SETTINGS_ROOT_PATH / "include/wifi_settings/wifi_settings_remote.h",
    PICO_WIFI_SETTINGS_ROOT_PATH / "include/wifi_settings/wifi_settings_hostname.h",
    PICO_WIFI_SETTINGS_ROOT_PATH / "src/wifi_settings_remote.c",
]
PYTHON_MODULES = [
    wifi_settings,
    wifi_settings.protocol,
    wifi_settings.version,
    wifi_settings.configuration, 
]
NOT_REQUIRED_IN_PYTHON = set([
    "AES_KEY_SIZE",
    "APPEND_CODE_SIZE",
    "HMAC_BLOCK_SIZE",
    "HMAC_DIGEST_SIZE",
    "MAX_HOSTNAME_SIZE",
    "SEND_GREETING",
    "WIFI_BSSID_SIZE",
    "WIFI_PASSWORD_SIZE",
    "WIFI_SSID_SIZE",
])
REQUIRED_IN_BOTH = set([
    "PROTOCOL_VERSION", "ID_REQUEST",
    "ID_FIRST_USER_HANDLER", "BOARD_ID_SIZE",
    "ID_LAST_USER_HANDLER",
])

def test_id_sync() -> None:
    error = False

    # Scan C files
    c_value: typing.Dict[str, int] = {}
    for scan_file in C_ID_FILES:
        for line in open(scan_file, "rt"):
            m = RE_DEFINE.match(line)
            if m is None:
                m = RE_ENUM.match(line)
            if m is not None:
                key = m.group(1)
                value = int(m.group(2))
                c_value[key] = value

    # Scan Python
    py_value: typing.Dict[str, int] = {}
    for module in PYTHON_MODULES:
        for key in dir(module):
            value = getattr(module, key)
            if isinstance(value, int):
                py_value[key] = value

    # Check that certain specific things appear in both places
    # (primarily as a test that the correct values have been gathered)
    for key in sorted(REQUIRED_IN_BOTH):
        if not (key in c_value):
            if not (key in py_value):
                print(f"Missing {key}: not in C or Python")
                error = True
            else:
                print(f"Missing {key}: not in C, appears in Python")
                error = True
        elif not (key in py_value):
            print(f"Missing {key}: not in Python, appears in C")
            error = True

    # Check that Python has the same things
    for (key, value) in sorted(c_value.items()):
        if key in py_value:
            check = py_value[key]
            if check != value:
                print(f"Mismatch for {key}: C has {value} Python has {check}")
                error = True
        elif not (key in NOT_REQUIRED_IN_PYTHON):
            print(f"Mismatch for {key}: appears in C as {value}, but not in Python")
            error = True

    if error:
        raise Exception("Error found")
