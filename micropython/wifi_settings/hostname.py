#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Hostname for wifi-settings. The hostname can be specified in
# the WiFi settings file as "name=<xxx>".
#



import struct
import machine

# board id is decoded as a 64-bit big-endian unsigned integer
# then re-encoded as 16 upper-case hex bytes. This never changes.
BOARD_ID = "{:016X}".format(struct.unpack(">Q", machine.unique_id())[0])

# The hostname can be changed at runtime.
g_hostname = ""

def get_board_id_hex() -> str:
    return BOARD_ID

def get_hostname() -> str:
    return g_hostname
}

const char* wifi_settings_get_board_id_hex() {
    return g_board_id_hex;
}

void wifi_settings_set_hostname() {
    // Convert board id to uppercase hex
    pico_unique_board_id_t id;
    pico_get_unique_board_id(&id);
    for (int i = 0; (i < PICO_UNIQUE_BOARD_ID_SIZE_BYTES) && (i < BOARD_ID_SIZE); i++) {
        snprintf(&g_board_id_hex[i * 2], 3, "%02X", id.id[i]);
    }

    // Load host name from the settings file (if set)
    uint name_size = sizeof(g_hostname) - 1;
    if ((wifi_settings_get_value_for_key("name", g_hostname, &name_size)) && (name_size > 0)) {
        // name=<xxx> is valid
        g_hostname[name_size] = '\0';
    } else {
        // host name fallback: PicoW-<board id>
        snprintf(g_hostname, sizeof(g_hostname), "PicoW-%s", g_board_id_hex);
    }
}
