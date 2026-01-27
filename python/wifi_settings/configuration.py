"""
Protocol constants

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

BOARD_ID_SIZE = 8 
MAX_DATA_SIZE = 4096
PORT_NUMBER = 1404
REMOTE_PICOTOOL_CFG_NAME = "remote_picotool.cfg"

# Version to report via info messages
WIFI_SETTINGS_VERSION_STRING = "0.3.1"

# Maximum time allowed between calling cyw43_wifi_join and getting an
# IP address (milliseconds). If this timeout expires, wifi_settings will
# try a different hotspot or rescan. The attempt to join a hotspot can fail
# sooner than this, e.g. if the password is incorrect or the hotspot vanishes.
CONNECT_TIMEOUT_TIME_MS = 30000

# Minimum time between scans (milliseconds). If a scan fails to find any
# known hotspot, wifi_settings will always wait at least this long before
# retry.
REPEAT_SCAN_TIME_MS = 3000

# Minimum time between calls to the periodic function, __periodic_callback,
# which will initiate scans and connections if necessary (milliseconds).
PERIODIC_TIME_MS = 1000

# Maximum number of SSIDs that can be supported. This determines the size
# of the g_wifi_state.ssid_scan_info list.
MAX_NUM_SSIDS = 100

# wifi-settings file name
WIFI_SETTINGS_FILE_NAME = "/wifi.cfg"
