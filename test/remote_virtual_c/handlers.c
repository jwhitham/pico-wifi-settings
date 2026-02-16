/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"
#include "remote_virtual.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled"
#endif

static char g_expected_arg_address[1];

#define ID_TEST_HANDLER_ECHO_XOR_COUNT  (ID_FIRST_USER_HANDLER + 0)
#define ID_TEST_HANDLER_GEN_OUTPUT      (ID_FIRST_USER_HANDLER + 1)
#define ID_TEST_HANDLER_BOUNDS_CHECK    (ID_FIRST_USER_HANDLER + 2)


// This test handler echoes the input back, XOR'ing it with a constant 0xac.
// The input parameter is expected to be -input_data_size.
// The output value is -10 minus the number of 0x41 bytes in the input data.

int32_t test_handler_echo_xor_count(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    printf("test_handler_echo_xor_count: %u %d\n", (unsigned) input_data_size, (int) input_parameter);
    ASSERT(msg_type == ID_TEST_HANDLER_ECHO_XOR_COUNT);
    ASSERT(arg == g_expected_arg_address);
    ASSERT(*output_data_size == MAX_DATA_SIZE);
    ASSERT(input_data_size <= MAX_DATA_SIZE);
    if ((int) (-input_parameter) != (int) input_data_size) {
        *output_data_size = 0;
        return -1;
    }

    int32_t value = -10;
    for (uint32_t i = 0; i < input_data_size; i++) {
        if (data_buffer[i] == 0x41) {
            value -= 1;
        }
        data_buffer[i] ^= 0xac;
    }
    *output_data_size = input_data_size;
    printf("test_handler_echo_xor_count: return %d\n", value);
    return value;
}

// This test handler generates output. The input parameter specifies the
// number of bytes to generate.
int32_t test_handler_gen_output(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    printf("test_handler_gen_output: %u %d\n", (unsigned) input_data_size, (int) input_parameter);
    ASSERT(msg_type == ID_TEST_HANDLER_GEN_OUTPUT);
    ASSERT(arg == g_expected_arg_address);
    ASSERT(*output_data_size == MAX_DATA_SIZE);
    ASSERT(input_data_size == 0);

    if (input_parameter > MAX_DATA_SIZE) {
        *output_data_size = MAX_DATA_SIZE;
    } else if (input_parameter <= 0) {
        *output_data_size = 0;
    } else {
        *output_data_size = (uint32_t) input_parameter;
    }
    for (uint32_t i = 0; i < *output_data_size; i++) {
        data_buffer[i] = (uint8_t) (i + 1);
    }
    return input_parameter ^ 1;
}

// This test handler produces no output bytes. It checks the bounds of the inputs and outputs.

int32_t test_handler_bounds_check(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    printf("test_handler_bounds_check: %u %d\n", (unsigned) input_data_size, (int) input_parameter);
    ASSERT(msg_type == ID_TEST_HANDLER_BOUNDS_CHECK);
    ASSERT(arg == g_expected_arg_address);
    ASSERT(*output_data_size == MAX_DATA_SIZE);
    ASSERT(input_data_size <= MAX_DATA_SIZE);

    *output_data_size = 0;
    switch (input_parameter) {

        case INT_MIN:
            return -1;
        case INT_MAX:
            return -2;
        case -1:
            return INT_MIN;
        case -2:
            return INT_MAX;
        case -3:
            return (int32_t) ((int64_t) INT_MAX + 1LL);
        case -4:
            return (int32_t) ((int64_t) INT_MIN - 1LL);
        case -5:
            return (int32_t) ((int64_t) 0x123456789abcdeLL);
        default:
            if (input_data_size == input_parameter)
            {
                return -3;
            } else {
                return -4;
            }
    }
}

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
        "name=test-host-name\n"
        "id_last_user_handler=%d\n"
        "max_data_size=%d\n"
        "implementation=TestC\n",
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

void register_handlers(void) {
    wifi_settings_remote_set_handler(ID_TEST_HANDLER_ECHO_XOR_COUNT,
            test_handler_echo_xor_count, g_expected_arg_address);
    wifi_settings_remote_set_handler(ID_TEST_HANDLER_GEN_OUTPUT,
            test_handler_gen_output, g_expected_arg_address);
    wifi_settings_remote_set_handler(ID_TEST_HANDLER_BOUNDS_CHECK,
            test_handler_bounds_check, g_expected_arg_address);
}

