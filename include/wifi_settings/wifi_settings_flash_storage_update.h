/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This header file declares functions used to update the WiFi settings
 * and other key/value data in Flash.
 *
 */

#ifndef _WIFI_SETTINGS_FLASH_STORAGE_UPDATE_H_
#define _WIFI_SETTINGS_FLASH_STORAGE_UPDATE_H_

#include "pico/stdlib.h"
#include <stdbool.h>
#include <stdint.h>

/// @brief Replace the settings file in Flash without using flash_safe_execute
/// (this should only be used if the other CPU core is locked out).
/// @param[in] file Pointer to replacement file data
/// @param[in] file_size Size of file: maximum is the size set by
/// wifi_settings_range_get_wifi_settings_file()
/// @return PICO_OK if updated successfully, or PICO_ERROR_...
int wifi_settings_update_flash_unsafe(
            const char* file,
            const uint file_size);

/// @brief Replace the settings file in Flash using flash_safe_execute.
/// @param[in] file Pointer to replacement file data
/// @param[in] file_size Size of file: maximum is the size set by
/// wifi_settings_range_get_wifi_settings_file()
/// @return PICO_OK if updated successfully, or PICO_ERROR_...
int wifi_settings_update_flash_safe(
            const char* file,
            const uint file_size);

#endif
