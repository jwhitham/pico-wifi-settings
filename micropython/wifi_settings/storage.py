#
#  Copyright (c) 2025 Jack Whitham
# 
#  SPDX-License-Identifier: BSD-3-Clause
# 
#  This module declares a function used to access the WiFi settings
#  and other key/value data in Flash.
# 
#

from . import configuration

# Type-checking
try:
    import typing
except ImportError:
    pass

class KeyValueStore:
    """Represents a key=value store such as the wifi-settings file.

    KeyValueStore is also used for remote_picotool.cfg and ID_PICO_INFO_HANDLER data."""

    END_OF_LINE_BYTES = b"\r\n\x00\xff\x1b"

    def __init__(self, contents: bytes = b"") -> None:
        """Create object representing key=value store."""
        self.contents = contents

    def find_index(self, key: str) -> typing.Optional[typing.Tuple[int, int, int]]:
        """Find the space occupied by key=value"""
        key_bytes = ("\n" + key + "=").encode("utf-8")
        if self.contents.startswith(key_bytes[1:]):
            # key=value at the beginning of the file
            key_index = 0
        else:
            # key=value elsewhere in the file?
            key_index = self.contents.find(key_bytes)
            if key_index < 0:
                # not present
                return None
            key_index += 1 # skip '\n'

        # find start and end of value
        value_index = key_index + len(key_bytes) - 1
        end_index = value_index
        while ((end_index < len(self.contents))
        and (self.contents[end_index] not in self.END_OF_LINE_BYTES)):
            end_index += 1
        
        return (key_index, value_index, end_index)

    def get(self, key: str, errors: str = "ignore") -> typing.Optional[str]:
        """Get a value for a key or return None.

        The encoding for values is UTF-8. The errors parameter
        is passed to the decode() function to specify how invalid UTF-8
        characters should be handled e.g. "ignore", "strict", "replace".
        """
        found = self.find_index(key)
        if not found:
            return None
    
        (_, value_index, end_index) = found
        return self.contents[value_index : end_index].decode("utf-8", errors=errors)

def get_value_for_key(key: str) -> typing.Optional[str]:
    """Scan the settings file in Flash for a particular key.

    If found, return the value as a string. If not found, return None.
    """
    try:
        with open(configuration.WIFI_SETTINGS_FILE_NAME, "rb") as fd:
            return KeyValueStore(fd.read()).get(key)
    except OSError:
        return None
