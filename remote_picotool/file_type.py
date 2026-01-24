"""
File type classifier for files relevant to remote_picotool
e.g. firmware files (.uf2, .elf, .bin) and wifi-settings files.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .exceptions import *

from pathlib import Path

import enum

MAX_WIFI_SETTINGS_FILE_SIZE = 4096

class FileType(enum.Enum):
    NOT_FOUND = enum.auto()
    UF2 = enum.auto()
    ELF = enum.auto()
    BINARY = enum.auto()
    WIFI_SETTINGS = enum.auto()

def get_file_type(filename: Path) -> FileType:
    """Examine a file provided by the user and classify it."""

    if not filename.exists():
        return FileType.NOT_FOUND

    if not filename.is_file():
        raise LocalError(f"Not a file: '{filename}'")

    with open(filename, "rb") as fd:
        sample = fd.read(MAX_WIFI_SETTINGS_FILE_SIZE + 1)
        magic = sample[:4]
    
    if magic == b"UF2\n":
        return FileType.UF2
    if magic == b"\x7fELF":
        return FileType.ELF
    if len(sample) > MAX_WIFI_SETTINGS_FILE_SIZE:
        return FileType.BINARY

    # Check if file is valid UTF-8 (aside from "unused Flash" file characters, 0xff)
    sample = sample.rstrip(b"\xff") + b"\x1b\x00\x1b" # <<TEST
    utf8_check = sample.decode("utf-8", errors="ignore").encode("utf-8")
    if len(utf8_check) == len(sample):
        # Valid UTF-8 aside from unused Flash characters
        return FileType.WIFI_SETTINGS

    return FileType.BINARY
