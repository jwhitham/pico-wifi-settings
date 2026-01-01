#
#  Copyright (c) 2025 Jack Whitham
# 
#  SPDX-License-Identifier: BSD-3-Clause
# 
#  This pico-wifi-settings module manages the WiFi connection
#  by calling network.WLAN functions.
# 
#

import typing

def get_value_for_key(key: str) -> typing.Optional[str]:
    """Scan the settings file in Flash for a particular key.

    If found, return the value as a string. If not found, return None.
    """
