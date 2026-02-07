/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled"
#endif


int32_t wifi_settings_pico_info_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    *output_data_size = snprintf(data_buffer, *output_data_size,
        "board_id=123456789ABCDEF0\n"
        "wifi_settings_version=%s\n"
        "name=test\n"
        "id_last_user_handler=%d\n"
        "max_data_size=%d\n"
        "implementation=C\n",
        WIFI_SETTINGS_VERSION_STRING,
        ID_LAST_USER_HANDLER,
        MAX_DATA_SIZE);
    return *output_data_size;
}

int32_t wifi_settings_update_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

int32_t wifi_settings_reboot_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

int32_t wifi_settings_update_reboot_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

void wifi_settings_update_reboot_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg)
{
}

#ifdef ENABLE_REMOTE_MEMORY_ACCESS
int32_t wifi_settings_read_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

int32_t wifi_settings_write_flash_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

int32_t wifi_settings_ota_firmware_update_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    *output_data_size = 0;
    return -1;
}

void wifi_settings_ota_firmware_update_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg) {
}

#endif

const char* wifi_settings_get_board_id_hex() {
    return "012345679ABCDEF";
}
