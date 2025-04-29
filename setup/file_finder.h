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

#ifndef PROBE_FILE_H 
#define PROBE_FILE_H 

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    FILE_IS_CORRUPT = 0,
    FILE_HAS_WIFI_DETAILS,
    FILE_HAS_PLACEHOLDER,
    FILE_IS_EMPTY,
} file_status_t;

void file_finder_init();
file_status_t file_finder_get_status();
void file_finder_get_status_text(char* text, int text_size);
void file_finder_set_address(uint32_t address);
bool file_finder_set_address_with_format(uint32_t address);
bool file_finder_set_address_with_move(uint32_t from_address, uint32_t to_address);


#endif
