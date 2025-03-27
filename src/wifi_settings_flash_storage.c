/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This pico-wifi-settings module reads and updates WiFi settings
 * information in Flash.
 *
 */

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_flash_storage.h"
#include "wifi_settings/wifi_settings_flash_range.h"

#include "hardware/flash.h"
#include "hardware/sync.h"

#include "pico/error.h"
#include "pico/flash.h"
#include "pico/stdlib.h"

#include <string.h>


bool wifi_settings_get_value_for_key_within_file(
            const char* file, const uint file_size,
            const char* key,
            char* value, uint* value_size) {

    enum parse_state_t {
        NEW_LINE,
        KEY,
        SEPARATOR,
        VALUE,
        WAIT_FOR_NEW_LINE,
    } parse_state = NEW_LINE;
    uint value_index = 0;
    uint key_index = 0;

    if (key[0] == '\0') {
        // Invalid key - must contain at least 1 character
        return false;
    }

    for (uint file_index = 0;
            (file_index < file_size)
            && (file[file_index] != '\0')
            && (file[file_index] != '\x1a') // CPM EOF character
            && (file[file_index] != '\xff'); // Flash padding character
            file_index++) {

        if ((file[file_index] == '\n') || (file[file_index] == '\r')) {
            // End of line reached (Unix or DOS line endings)
            if (parse_state == VALUE) {
                // This is the end of the value
                *value_size = value_index;
                return true;
            } else {
                // Reset the parsing state
                parse_state = NEW_LINE;
                continue;
            }
        }

        switch (parse_state) {
            case NEW_LINE:
                // At the beginning of a new line - ignore whitespace before the key
                key_index = 0;
                if (key[key_index] == file[file_index]) {
                    // Matched the first character in the key
                    key_index++;
                    if (key[key_index] == '\0') {
                        // There is only one character in the key
                        parse_state = SEPARATOR;
                    } else {
                        // Match the other characters in the key
                        parse_state = KEY;
                    }
                } else {
                    // Non-matching character: a different key,
                    // a comment - wait for the next newline
                    parse_state = WAIT_FOR_NEW_LINE;
                }
                break;
            case KEY:
                if (key[key_index] == file[file_index]) {
                    // Still matching the key
                    key_index++;
                    if (key[key_index] == '\0') {
                        // There are no more characters in the key
                        parse_state = SEPARATOR;
                    }
                } else {
                    // Non-matching character in the key
                    parse_state = WAIT_FOR_NEW_LINE;
                }
                break;
            case SEPARATOR:
                if (file[file_index] == '=') {
                    // Key is recognised - copy the value
                    parse_state = VALUE;
                } else {
                    // Key is not immediately followed by '=': not valid
                    parse_state = WAIT_FOR_NEW_LINE;
                }
                break;
            case VALUE:
                if (value_index >= *value_size) {
                    // Unable to copy more value characters - value is complete
                    return true;
                } else {
                    value[value_index] = file[file_index];
                    value_index++;
                }
                break;
            case WAIT_FOR_NEW_LINE:
                // Do nothing in this state, as the state will be reset when
                // the next newline is seen
                break;
        }
    }
    if (parse_state == VALUE) {
        // Reached end of file while parsing the value - value is complete
        *value_size = value_index;
        return true;
    }
    // Key was not found
    return false;
}

#ifndef UNIT_TEST
bool wifi_settings_get_value_for_key(
            const char* key, char* value, uint* value_size) {
    wifi_settings_flash_range_t fr;
    wifi_settings_logical_range_t lr;

    wifi_settings_range_get_wifi_settings_file(&fr);
    wifi_settings_range_translate_to_logical(&fr, &lr);

    return wifi_settings_get_value_for_key_within_file(
            (const char*) lr.start_address,
            lr.size,
            key, value, value_size);
}

static inline bool wifi_settings_flash_range_verify(
            const wifi_settings_flash_range_t* fr,
            const char* data) {

    wifi_settings_logical_range_t lr;
    wifi_settings_range_translate_to_logical(fr, &lr);
    return memcmp(lr.start_address, data, lr.size) == 0;
}
#endif

int wifi_settings_update_flash_unsafe(
            const char* file,
            const uint file_size) {

    // Get memory range for wifi-settings file
    wifi_settings_flash_range_t fr;
    wifi_settings_range_get_wifi_settings_file(&fr);

    // Check that the new data will actually fit
    if (file_size > fr.size) {
        return PICO_ERROR_INVALID_ARG;
    }

    // Erase existing file in Flash
    uint32_t flags = save_and_disable_interrupts();
    flash_range_erase(fr.start_address, fr.size);
    restore_interrupts(flags);

    // Store new copy
    for (uint32_t offset = 0; offset < file_size; offset += FLASH_PAGE_SIZE) {
        uint8_t page_copy[FLASH_PAGE_SIZE];
        const uint32_t remaining_size = file_size - offset;

        if (remaining_size >= FLASH_PAGE_SIZE) {
            // This page is full size
            memcpy(page_copy, &file[offset], FLASH_PAGE_SIZE);
        } else {
            // Page is incomplete and padded with '\xff' (Flash erase byte)
            memset(page_copy, '\xff', FLASH_PAGE_SIZE);
            memcpy(page_copy, &file[offset], remaining_size);
        }
        flags = save_and_disable_interrupts();
        flash_range_program(fr.start_address + offset, page_copy, FLASH_PAGE_SIZE);
        restore_interrupts(flags);
    }

    // Test copy
    fr.size = file_size;
    if (wifi_settings_flash_range_verify(&fr, file)) {
        if (file_size < WIFI_SETTINGS_FILE_SIZE) {
            // Check file is terminated by '\xff'
            fr.start_address += file_size;
            fr.size = 1;
            if (wifi_settings_flash_range_verify(&fr, "\xff")) {
                return PICO_OK;
            }
        } else {
            return PICO_OK;
        }
    }
    return PICO_ERROR_INVALID_DATA;
}

typedef struct wifi_settings_flash_safe_params_t {
    const char* file;
    uint32_t file_size;
    int rc;
} wifi_settings_flash_safe_params_t;

static void wifi_settings_flash_safe_internal(void* tmp) {
    wifi_settings_flash_safe_params_t* param = (wifi_settings_flash_safe_params_t*) tmp;
    param->rc = wifi_settings_update_flash_unsafe(param->file, param->file_size);
}

int wifi_settings_update_flash_safe(
            const char* file,
            const uint file_size) {
    wifi_settings_flash_safe_params_t param;
    param.file = (const char*) file;
    param.file_size = (uint32_t) file_size;
    param.rc = PICO_ERROR_GENERIC;
    int rc = flash_safe_execute(wifi_settings_flash_safe_internal, &param, ENTER_EXIT_TIMEOUT_MS);
    if (rc == PICO_OK) {
        return param.rc;
    } else {
        return rc;
    }
}

