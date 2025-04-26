/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This pico-wifi-settings module updates WiFi settings
 * information in Flash.
 *
 */

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_flash_storage_update.h"
#include "wifi_settings/wifi_settings_flash_range.h"

#include "hardware/flash.h"
#include "hardware/sync.h"

#include "pico/error.h"
#include "pico/flash.h"
#include "pico/stdlib.h"

#include <string.h>

#ifndef UNIT_TEST
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
