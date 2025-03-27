/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"
#include "wifi_settings/wifi_settings_flash_storage.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled"
#endif


handler_callback_result_t wifi_settings_pico_info_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {

    if (*output_data_size < sizeof(pico_info_t)) {
        return CALLBACK_PARAM_ERROR;
    }

    *output_data_size = sizeof(pico_info_t);
    pico_info_t* pico_info = (pico_info_t*) data_buffer;
    memset(pico_info, 0, sizeof(pico_info_t));

    memset(pico_info->board_id, 0xaa, sizeof(pico_info->board_id));
    strcpy(pico_info->board_name, "fake_handlers");
    pico_info->chip_id = 0xaabbcc;
    pico_info->wifi_settings_version = 0xdef;

    *output_parameter = strlen(pico_info->board_name);
    return CALLBACK_OK;
}

handler_callback_result_t wifi_settings_update_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {
    *output_data_size = 0;
    *output_parameter = 0;
    return CALLBACK_FAILURE_ERROR;
}

handler_callback_result_t wifi_settings_reboot_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {
    *output_data_size = 0;
    *output_parameter = 0;
    return CALLBACK_FAILURE_ERROR;
}

handler_callback_result_t wifi_settings_update_reboot_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {
    *output_data_size = 0;
    *output_parameter = 0;
    return CALLBACK_FAILURE_ERROR;
}

#ifdef ENABLE_REMOTE_MEMORY_ACCESS
handler_callback_result_t wifi_settings_read_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {
    *output_data_size = 0;
    *output_parameter = 0;
    return CALLBACK_FAILURE_ERROR;
}

handler_callback_result_t wifi_settings_write_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        uint32_t input_parameter,
        uint32_t* output_data_size,
        uint32_t* output_parameter,
        void* arg) {
    *output_data_size = 0;
    *output_parameter = 0;
    return CALLBACK_FAILURE_ERROR;
}
#endif
