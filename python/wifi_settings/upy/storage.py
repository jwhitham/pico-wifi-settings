#
#  Copyright (c) 2025 Jack Whitham
# 
#  SPDX-License-Identifier: BSD-3-Clause
# 
#  This module declares a function used to access the WiFi settings
#  and other key/value data in Flash.
# 
#

from .. import configuration
from .. import key_value_store
from .. import typing_shim as typing

def get_value_for_key(key: str) -> typing.Optional[str]:
    """Scan the settings file in Flash for a particular key.

    If found, return the value as a string. If not found, return None.
    """
    try:
        with open(configuration.WIFI_SETTINGS_FILE_NAME, "rb") as fd:
            return key_value_store.KeyValueStore(fd.read()).get(key)
    except OSError:
        return None
