"""
Remote access protocol client for pico-wifi-settings.

This module provides the implementation for the "remote_picotool" client.

Pico firmware built with the wifi-settings library, an 'update_secret'
and the -DWIFI_SETTINGS_REMOTE build option can be remotely controlled
and updated using this program.

See https://github.com/jwhitham/pico-wifi-settings

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

if __name__ == "__main__":
    from .aio.remote_picotool_main import main
    main()
