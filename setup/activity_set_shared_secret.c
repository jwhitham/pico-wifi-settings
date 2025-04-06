/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Set the update_secret in the settings file
 */

#include "activity_set_shared_secret.h"

#include "user_interface.h"
#include "edit_key_value.h"
#include "file_operations.h"
#include "wifi_settings.h"

#include <stdio.h>
#include <string.h>
#include <stdbool.h>


static bool accept_update_secret(const char* key, char* value) {
    if (strlen(value) == 0) {
        printf("If %s is empty, then remote update features\n"
            "are disabled. Really leave it empty? ", key);
        return ui_choose_yes_or_no();
    }
    return true;
}

void activity_set_shared_secret() {
    ui_clear();

    file_handle_t fh;
    file_load(&fh);

    const char* key = "update_secret";
    if (!file_contains(&fh, key)) {
        printf("The WiFi settings file has no update_secret defined!\n"
            "If an update_secret is defined, then remote_picotool can update\n"
            "the WiFi settings file remotely. For more information, please visit\n"
            "%s\n\n"
            "Would you like to set an update_secret?\n", WIFI_SETTINGS_PROJECT_URL);
        if (!ui_choose_yes_or_no()) {
            return;
        }
    } else {
        printf("For more information about using update_secret for remote\n"
            "updates, see %s\n", WIFI_SETTINGS_PROJECT_URL);
    }
    edit_key_value(&fh, key, NULL, true, accept_update_secret);
#ifdef ENABLE_REMOTE_UPDATE
    wifi_settings_remote_update_secret();
#endif
}
