/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Force disconnect/reconnect from WiFi
 */

#include "activity_force_disconnect_reconnect.h"
#include "user_interface.h"

#include "wifi_settings.h"
#include <stdio.h>

void activity_force_disconnect_reconnect() {
    ui_clear();
    if (wifi_settings_is_connected()) {
        wifi_settings_disconnect();
    } else {
        wifi_settings_disconnect();
        wifi_settings_connect();
    }
}
