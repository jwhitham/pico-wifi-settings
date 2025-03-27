/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Editor function for a generic key
 */


#include "edit_key_value.h"
#include "file_operations.h"
#include "user_interface.h"

#include <string.h>
#include <stdio.h>


bool edit_key_value(
            file_handle_t* fh,
            const char* key,
            const char* custom_description,
            bool always_discard_when_empty,
            key_value_accept_callback_t accept_callback) {

    char value[MAX_EDIT_LINE_LENGTH];

    // The caller can give an initial value for new keys using key=value form,
    // check if this leaves the key empty
    char* separator = strstr(key, "=");
    if (separator != NULL) {
        separator[0] = '\0';
    }
    if (strlen(key) == 0) {
        printf("Keys cannot be empty.\n");
        ui_wait_for_the_user();
        return true;
    }
    if (separator == NULL) {
        // Load existing value from the file
        strcpy(value, "");
        const int value_size = file_get(fh, key, value, sizeof(value));
        if (value_size > MAX_EDIT_LINE_LENGTH) {
            printf("The WiFi settings file has a value for %s,\n"
                   "but unfortunately it is too long to be edited with this tool.\n"
                   "The maximum value size is %d, this value size is %d.\n"
                   "You can edit it by one of the other means described on\n"
                   "%s\n\n", key,
                   MAX_EDIT_LINE_LENGTH - 1, value_size - 1,
                   WIFI_SETTINGS_PROJECT_URL);
            ui_wait_for_the_user();
            return true;
        }
    } else {
        // Load existing value from key=value input
        strncpy(value, &separator[1], MAX_EDIT_LINE_LENGTH - 1);
        value[MAX_EDIT_LINE_LENGTH - 1] = '\0';
    }
    while (true) {
        if (custom_description != NULL) {
            printf("%s", custom_description);
        } else {
            printf("Set the value for %s:\n", key);
        }

        if (!ui_text_entry(value, sizeof(value))) {
            return false; // cancel
        }
        if (strlen(value) == 0) {
            // If the value is empty, we might discard the key=value pair
            bool discard = false;
            if (always_discard_when_empty) {
                discard = true;
            } else {
                printf("The value is empty. Do you want to delete the key?\n"
                       "(If you answer 'no', the key will still exist, but with an empty value.)\n");
                discard = ui_choose_yes_or_no();
            }
            if (discard) {
                file_discard(fh, key);
                ui_file_save(fh);
                return true;
            }
        }
        if ((accept_callback == NULL) || accept_callback(key, value)) {
            // New value is acceptable
            file_set(fh, key, value);
            ui_file_save(fh);
            return true;
        }
    }
}
