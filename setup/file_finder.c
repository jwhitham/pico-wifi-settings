/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Functions to search for the WiFi settings file. There is a default
 * location (see wifi_settings_configuration.h) but the wifi-settings
 * library user can override it with -DWIFI_SETTINGS_FILE_ADDRESS=0x..
 * or by implementing wifi_settings_range_get_wifi_settings_file().
 *
 * In 0.1.x versions the default location was different.
 *
 */

#include "file_finder.h"
#include "file_operations.h"
#include "user_interface.h"

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_flash_range.h"
#include "wifi_settings/wifi_settings_connect.h"

#include <stdio.h>
#include <string.h>

#define SETUP_VERSION_KEY "pico-wifi-settings-setup-app"

static wifi_settings_flash_range_t g_wifi_settings_file_range = {0, 0};

typedef enum {
    NO_FILE = 0,
    FILE_AT_DEFAULT_ADDRESS,
    FILE_AT_CUSTOM_ADDRESS,
} probe_result_t;

// This overrides the definition in src/wifi_settings_range.c with an alternative
// that is determined dynamically.
void wifi_settings_range_get_wifi_settings_file(wifi_settings_flash_range_t* r) {
    memcpy(r, &g_wifi_settings_file_range, sizeof(wifi_settings_flash_range_t));
}

// Look for a Wifi settings file at g_wifi_settings_file_range
// Return information about the block at that location
file_status_t file_finder_get_status() {
    // Convert Flash address to a logical address that can be accessed by the CPU
    wifi_settings_logical_range_t lr;
    wifi_settings_range_translate_to_logical(&g_wifi_settings_file_range, &lr);
    const uint8_t* try_pointer = (const uint8_t*) lr.start_address;

    // Examine byte 0
    const uint8_t byte0 = *try_pointer;
    if ((byte0 == 0xff) || (byte0 == 0x00)) {
        // These values indicate end of file (0x00, 0xff).
        // This block will be treated as erased if all bytes are the same,
        // otherwise, this is a corrupt file.
        for (uint i = 1; i < lr.size; i++) {
            if (try_pointer[i] != byte0) {
                return FILE_IS_CORRUPT;
            }
        }
        return FILE_IS_EMPTY;
    }

    // Examine keys in the file
    // Any of "ssid1", "bssid1" or SETUP_VERSION_KEY indicate a valid file
    // We could also use wifi_settings_has_no_wifi_details() to detect
    // the first two, but it will be faster to work from a copy in RAM.
    file_handle_t fh;
    file_load(&fh);
    if (file_contains(&fh, "ssid1")
    || file_contains(&fh, "bssid1")) {
        return FILE_HAS_WIFI_DETAILS;
    } else if (file_contains(&fh, SETUP_VERSION_KEY)) {
        return FILE_HAS_PLACEHOLDER;
    } else {
        // File is not empty, but does not contain wifi settings either
        return FILE_IS_CORRUPT;
    }
}

// Look for a Wifi settings file at g_wifi_settings_file_range
// Return true if a non-empty file exists there
static bool valid_file_exists() {
    switch (file_finder_get_status()) {
        case FILE_HAS_WIFI_DETAILS:
        case FILE_HAS_PLACEHOLDER:
            return true;
        default:
            return false;
    }
}

// Search for a valid wifi-settings file on bootup
// (it could be anywhere in Flash not occupied by the program)
void file_finder_init() {
    // Reset search
    g_wifi_settings_file_range.size = WIFI_SETTINGS_FILE_SIZE;

    // First we check the default location
    const uint32_t default_address = WIFI_SETTINGS_FILE_ADDRESS;
    file_finder_set_address(default_address);
    if (valid_file_exists()) {
        return;
    }

    // Try addresses above the default location - this will include
    // the wifi-settings file address from version 0.1.x. Search upwards,
    // in case the file size is larger than the sector size.
    wifi_settings_flash_range_t flash_range;
    wifi_settings_range_get_all(&flash_range);
    const uint32_t end_of_flash = flash_range.start_address + flash_range.size;

    for (uint32_t try_address = default_address + WIFI_SETTINGS_FILE_SIZE;
                try_address <= (end_of_flash - WIFI_SETTINGS_FILE_SIZE);
                try_address += WIFI_SETTINGS_FILE_SIZE) {
        file_finder_set_address(try_address);
        if (valid_file_exists()) {
            return;
        }
    }

    // Now try lower addresses. Any address after the program is possible.
    wifi_settings_flash_range_t program_range;
    wifi_settings_range_get_program(&program_range);
    wifi_settings_range_align_to_sector(&program_range);
    const uint32_t end_of_program = program_range.start_address + program_range.size;

    // wifi-settings file could be anywhere between end_of_program and end_of_flash
    // but the address has to be aligned to a Flash sector. Try each possibility.
    for (uint32_t try_address = default_address - WIFI_SETTINGS_FILE_SIZE;
            try_address >= end_of_program;
            try_address -= WIFI_SETTINGS_FILE_SIZE) {
        file_finder_set_address(try_address);
        if (valid_file_exists()) {
            return;
        }
    }

    // The file wasn't found. Perhaps the user didn't configure it yet?
    // Use the default address
    file_finder_set_address(default_address);
}

// Set address for file
void file_finder_set_address(uint32_t address) {
    g_wifi_settings_file_range.start_address = address;
}

// Set address for file and reformat the block at the destination
bool file_finder_set_address_with_format(uint32_t address) {
    file_handle_t fh;
    memset(&fh, 0xff, sizeof(fh));
    file_set(&fh, SETUP_VERSION_KEY, WIFI_SETTINGS_VERSION_STRING);
    file_finder_set_address(address);
    return ui_file_save(&fh);
}

// Set address for file and move data from another location
bool file_finder_set_address_with_move(uint32_t from_address, uint32_t to_address) {
    file_handle_t fh;
    // load from old address
    file_finder_set_address(from_address);
    file_load(&fh);
    file_set(&fh, SETUP_VERSION_KEY, WIFI_SETTINGS_VERSION_STRING);
    // write to new address
    file_finder_set_address(to_address);
    if (ui_file_save(&fh)) {
        // Successfully moved to the new address, erase the old address
        memset(&fh, 0xff, sizeof(fh));
        file_finder_set_address(from_address);
        if (ui_file_save(&fh)) {
            // Successfully erased
            file_finder_set_address(to_address);
            return true;
        }
    }
    // Something went wrong - transfer failed
    file_finder_set_address(to_address);
    return false;
}

// Get a status report about the file
void file_finder_get_status_text(char* text, int text_size) {
    wifi_settings_flash_range_t r;
    wifi_settings_range_get_wifi_settings_file(&r);
    const uint32_t default_address = WIFI_SETTINGS_FILE_ADDRESS;

    switch (file_finder_get_status()) {
        case FILE_HAS_WIFI_DETAILS:
        case FILE_HAS_PLACEHOLDER:
            if (g_wifi_settings_file_range.start_address != default_address) {
                snprintf(text, text_size, "wifi-settings file found at custom location 0x%x",
                        (uint) g_wifi_settings_file_range.start_address);
            } else {
                snprintf(text, text_size, "wifi-settings file found at default location 0x%x",
                        (uint) g_wifi_settings_file_range.start_address);
            }
            break;
        case FILE_IS_CORRUPT:
            snprintf(text, text_size,
                    "wifi-settings file at 0x%x appears corrupt",
                   (uint) g_wifi_settings_file_range.start_address);
            break;
        default:
            snprintf(text, text_size,
                    "wifi-settings file will be created at default location 0x%x",
                    (uint) g_wifi_settings_file_range.start_address);
            break;
    }
}
