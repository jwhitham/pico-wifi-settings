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

#ifndef _WIFI_SETTINGS_REMOTE_HANDLERS_H_
#define _WIFI_SETTINGS_REMOTE_HANDLERS_H_

#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_hostname.h"
#include <stdbool.h>
#include <stdint.h>

/// @brief for ID_PICO_INFO_HANDLER messages:
int32_t wifi_settings_pico_info_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief for ID_UPDATE_HANDLER
int32_t wifi_settings_update_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief for ID_UPDATE_REBOOT_HANDLER (second stage)
void wifi_settings_update_reboot_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg);

#endif
