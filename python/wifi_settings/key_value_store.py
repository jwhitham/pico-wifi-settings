"""
Key-value store representation for pico-wifi-settings.

Represents a key=value store such as the wifi-settings file.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from . import typing_shim as typing

END_OF_LINE_BYTES = b"\r\n\x00\xff\x1b"

FlashRange: typing.TypeAlias = "typing.Tuple[int, int]"

class KeyValueStore:
    """Represents a key=value store such as the wifi-settings file.

    KeyValueStore is also used for remote_picotool.cfg and ID_PICO_INFO_HANDLER data."""

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
        and (self.contents[end_index] not in END_OF_LINE_BYTES)):
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

    def crop(self) -> None:
        """Remove end characters"""
        self.contents = self.contents.rstrip(END_OF_LINE_BYTES)

    def discard(self, key: str) -> None:
        """Discard all copies of a key"""
        found = self.find_index(key)
        while found:
            # What to remove?
            (key_index, _, end_index) = found
            # Also remove line endings and end-of-file characters
            while ((end_index < len(self.contents))
            and (self.contents[end_index] in END_OF_LINE_BYTES)):
                end_index += 1
            self.contents = self.contents[:key_index] + self.contents[end_index:]
            # Search again
            found = self.find_index(key)

    def set(self, key: str, value: str) -> None:
        """Set a new value for a key (discarding old values first if necessary)"""
        self.discard(key)
        self.crop()
        self.contents = (key + "=" + value + "\n").encode("utf-8") + self.contents

    def get_float(self, key: str, default_value: float = 0.0) -> float:
        """Get the value of a key as a float.

        If the value isn't defined, or can't be converted to a float, default_value is returned.
        """
        value = self.get(key)
        if value is None:
            return default_value
        try:
            return float(value)
        except ValueError:
            return default_value

    def get_int(self, key: str, default_value: int = 0) -> int:
        """Get the value of a key as an int.

        If the value isn't defined, or can't be converted to an int, default_value is returned.
        """
        value = self.get(key)
        if value is None:
            return default_value
        try:
            return int(value, 0)
        except ValueError:
            return default_value

    def get_str(self, key: str, default_value: str = "") -> str:
        """Get the value of a key as a string.

        If the value isn't defined, default_value is returned.
        """
        value = self.get(key)
        if value is None:
            return default_value
        else:
            return value

    def get_range(self, key: str) -> FlashRange:
        """Get the value of a key as a FlashRange <x>:<y>.

        If the value isn't defined, (0, 0) is returned.
        """
        value = self.get(key)
        if value is None:
            return (0, 0)
        (start, _, end) = value.partition(":")
        try:
            return (int(start, 0), int(end, 0))
        except ValueError:
            return (0, 0)
