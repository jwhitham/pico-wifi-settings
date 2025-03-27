/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This header file declares built-in handlers for the remote update service for
 * pico-wifi-settings. This header file is intended only for internal use.
 * You would normally only need to include "wifi_settings.h" in your application.
 *
 */

#ifndef _WIFI_SETTINGS_REMOTE_MEMORY_ACCESS_HANDLERS_H_
#define _WIFI_SETTINGS_REMOTE_MEMORY_ACCESS_HANDLERS_H_

#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_hostname.h"
#include "wifi_settings/wifi_settings_flash_range.h"
#include <stdbool.h>
#include <stdint.h>

#define WIFI_SETTINGS_OTA_HASH_SIZE 32

// structure received by ID_OTA_FIRMWARE_UPDATE_HANDLER
typedef struct ota_firmware_update_parameter_t {
    wifi_settings_flash_range_t copy_from;
    wifi_settings_flash_range_t copy_to;
    uint8_t hash[WIFI_SETTINGS_OTA_HASH_SIZE];
} ota_firmware_update_parameter_t;

// structure received by ID_READ_HANDLER
typedef struct read_parameter_t {
    wifi_settings_logical_range_t copy_from;
} read_parameter_t;

/// @brief for ID_READ_HANDLER
int32_t wifi_settings_read_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief for ID_WRITE_FLASH_HANDLER
/// @param[in] input_data_size data to write must be a whole number of Flash sectors
/// @param[in] input_parameter target Flash address (0 = start of Flash)
int32_t wifi_settings_write_flash_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief for ID_OTA_FIRMWARE_UPDATE_HANDLER (first stage)
int32_t wifi_settings_ota_firmware_update_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief for ID_OTA_FIRMWARE_UPDATE_HANDLER (second stage)
void wifi_settings_ota_firmware_update_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg);

#endif
