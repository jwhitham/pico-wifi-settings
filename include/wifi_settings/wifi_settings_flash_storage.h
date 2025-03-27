/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This header file declares functions used to access the WiFi settings
 * and other key/value data in Flash.
 *
 */

#ifndef _WIFI_SETTINGS_FLASH_STORAGE_H_
#define _WIFI_SETTINGS_FLASH_STORAGE_H_

#include "pico/stdlib.h"
#include <stdbool.h>
#include <stdint.h>

#define ENTER_EXIT_TIMEOUT_MS   100

/// @brief Scan a Wifi settings file for a particular key.
/// If found, copy up to *value_size characters to value.
/// Note: value will not be '\0' terminated.
/// @param[in] file Pointer to beginning of file block
/// @param[in] file_size Size of file block (typically FLASH_SECTOR_SIZE)
/// @param[in] key Key to be found ('\0' terminated)
/// @param[out] value Value for key (if found) - not '\0' terminated
/// @param[inout] value_size Size of the value
/// @return true if key found
bool wifi_settings_get_value_for_key_within_file(
            const char* file, const uint file_size,
            const char* key,
            char* value, uint* value_size);

/// @brief Scan the settings file in Flash for a particular key.
/// If found, copy up to *value_size characters to value.
/// Note: value will not be '\0' terminated.
/// @param[in] key Key to be found ('\0' terminated)
/// @param[out] value Value for key (if found) - not '\0' terminated
/// @param[inout] value_size Size of the value
/// @return true if key found
bool wifi_settings_get_value_for_key(
            const char* key,
            char* value, uint* value_size);

/// @brief Replace the settings file in Flash without using flash_safe_execute
/// (this should only be used if the second CPU core is locked out).
/// @param[in] file Pointer to replacement file data
/// @param[in] file_size Size of file (no more than WIFI_SETTINGS_FILE_SIZE)
/// @return PICO_OK if updated successfully, or PICO_ERROR_...
int wifi_settings_update_flash_unsafe(
            const char* file,
            const uint file_size);

/// @brief Replace the settings file in Flash using flash_safe_execute.
/// @param[in] file Pointer to replacement file data
/// @param[in] file_size Size of file (no more than WIFI_SETTINGS_FILE_SIZE)
/// @return PICO_OK if updated successfully, or PICO_ERROR_...
int wifi_settings_update_flash_safe(
            const char* file,
            const uint file_size);

#endif
