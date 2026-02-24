/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"

#ifdef ENABLE_REMOTE_MEMORY_ACCESS
#include "wifi_settings/wifi_settings_remote_memory_access_handlers.h"
#endif

#include "remote_virtual.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <unistd.h>
#include <fcntl.h>

#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled"
#endif

#define ID_TEST_HANDLER_ECHO_XOR_COUNT  (ID_FIRST_USER_HANDLER + 0)
#define ID_TEST_HANDLER_GEN_OUTPUT      (ID_FIRST_USER_HANDLER + 1)
#define ID_TEST_HANDLER_BOUNDS_CHECK    (ID_FIRST_USER_HANDLER + 2)

#define FAKE_FLASH_SECTOR_SIZE          (MAX_DATA_SIZE / 2)

// These addresses are relative to the start of Flash
#define FAKE_FLASH_PROGRAM_START        (0)
#define FAKE_FLASH_REUSABLE_START       (MAX_DATA_SIZE * 4)
#define FAKE_FLASH_WIFI_SETTINGS_START  (MAX_DATA_SIZE * 8)
#define FAKE_FLASH_WIFI_SETTINGS_END    (MAX_DATA_SIZE * 9)
// Addresses based on the Flash start address are also used for
// flash_all, flash_reusable, flash_wifi_settings_file, flash_program,
// and for the write and ota handlers.
// logical_offset is the difference at the start of Flash.

static char g_expected_arg_address[1];
static char g_fake_flash[FAKE_FLASH_WIFI_SETTINGS_START - FAKE_FLASH_REUSABLE_START];

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
        "id_last_user_handler=%d\n"
        "max_data_size=%d\n"
        "flash_sector_size=%d\n"
        "flash_all=0x%08x:0x%08x\n"
        "flash_program=0x%08x:0x%08x\n"
        "flash_reusable=0x%08x:0x%08x\n"
        "flash_wifi_settings_file=0x%08x:0x%08x\n"
        "wifi_settings_version=%s\n"
        "program=Test\n"
        "feature=Feature\n"
        "board_id=123456789ABCDEF0\n"
        "implementation=TestC\n"
        "type_name=Type\n"
        "name=test-host-name\n",
        ID_LAST_USER_HANDLER,
        MAX_DATA_SIZE,  // max_data_size
        FAKE_FLASH_SECTOR_SIZE,  // flash_sector_size
        FAKE_FLASH_PROGRAM_START, FAKE_FLASH_WIFI_SETTINGS_END, // flash_all
        FAKE_FLASH_PROGRAM_START, FAKE_FLASH_REUSABLE_START, // flash_program_range
        FAKE_FLASH_REUSABLE_START, FAKE_FLASH_WIFI_SETTINGS_START, // flash_reusable_range
        FAKE_FLASH_WIFI_SETTINGS_START, FAKE_FLASH_WIFI_SETTINGS_END, // flash_wifi_settings_file_range
        WIFI_SETTINGS_VERSION_STRING);
    printf("pico_info_handler returns:\n%s\nEND\n", (const char*) data_buffer);
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
    printf("wifi_settings_update_handler %d %u\n", (int) input_parameter, (unsigned) input_data_size);

    if (input_parameter != 0) {
        return PICO_ERROR_INVALID_ARG;
    }

    int fd = open("wifi_settings.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        write(fd, data_buffer, input_data_size);
        close(fd);
    }
    return (int32_t) input_data_size;
}

int32_t wifi_settings_update_reboot_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {
    printf("wifi_settings_update_reboot_handler1 %d %u\n", (int) input_parameter, (unsigned) input_data_size);
    *output_data_size = input_data_size;
    return input_parameter;
}

void wifi_settings_update_reboot_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg)
{
    printf("wifi_settings_update_reboot_handler2 %d %u\n", (int) input_parameter, (unsigned) input_data_size);

    if (input_data_size != 0) {
        int fd = open("wifi_settings.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd >= 0) {
            write(fd, data_buffer, input_data_size);
            close(fd);
        }
    }

    int fd = open("reboot.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        uint8_t flag = (uint8_t) input_parameter;   // 1 = bootloader 0 = just reboot
        write(fd, &flag, 1);
        close(fd);
    }
}

#ifdef ENABLE_REMOTE_MEMORY_ACCESS
typedef struct read_parameter_t {
    wifi_settings_logical_range_t copy_from;
} read_parameter_t;
int32_t wifi_settings_read_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    *output_data_size = 0;
    if ((input_data_size != sizeof(read_parameter_t))
    || (input_parameter != 0)) {
        return PICO_ERROR_INVALID_ARG;
    }

    read_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(read_parameter_t));

    const uint32_t base_address = (uint32_t) input_parameter;
    const uint32_t limit_address = base_address + input_data_size;
    printf("write_flash_handler: %u bytes to 0x%x\n",
        (unsigned) input_data_size, (unsigned) base_address);

    const uint32_t alignment_mask = FAKE_FLASH_SECTOR_SIZE - 1;
    if (((input_data_size & alignment_mask) != 0)
    || ((base_address & alignment_mask) != 0)) {
        return PICO_ERROR_BAD_ALIGNMENT;
    }
    if ( !((base_address >= FAKE_FLASH_REUSABLE_START)
            && (base_address < limit_address)
            && (limit_address <= FAKE_FLASH_WIFI_SETTINGS_START))) {
        return PICO_ERROR_INVALID_ADDRESS;
    }
    return -1;

}

int32_t wifi_settings_write_flash_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    ASSERT(input_data_size <= MAX_DATA_SIZE);
    ASSERT(*output_data_size == MAX_DATA_SIZE);
    *output_data_size = 0;

    const uint32_t base_address = (uint32_t) input_parameter;
    const uint32_t limit_address = base_address + input_data_size;
    printf("write_flash_handler: %u bytes to 0x%x\n",
        (unsigned) input_data_size, (unsigned) base_address);

    const uint32_t alignment_mask = FAKE_FLASH_SECTOR_SIZE - 1;
    if (((input_data_size & alignment_mask) != 0)
    || ((base_address & alignment_mask) != 0)) {
        return PICO_ERROR_BAD_ALIGNMENT;
    }
    if ( !((base_address >= FAKE_FLASH_REUSABLE_START)
            && (base_address < limit_address)
            && (limit_address <= FAKE_FLASH_WIFI_SETTINGS_START))) {
        return PICO_ERROR_INVALID_ADDRESS;
    }

    memcpy(&g_fake_flash[base_address - FAKE_FLASH_REUSABLE_START],
           data_buffer, input_data_size);
    return 0;
}
static int check_ota_parameters(const uint8_t* data_buffer, int stage) {
    ota_firmware_update_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(ota_firmware_update_parameter_t));

    const uint32_t base_src_address = parameter.copy_from.start_address;
    const uint32_t limit_src_address = base_src_address + parameter.copy_from.size;
    const uint32_t src_size = parameter.copy_from.size;
    const uint32_t base_dest_address = parameter.copy_to.start_address;
    const uint32_t limit_dest_address = base_dest_address + parameter.copy_to.size;
    const uint32_t dest_size = parameter.copy_to.size;

    printf("ota_firmware_update_handler: stage %d: %u bytes from 0x%x to 0x%x\n",
        stage,
        (unsigned) src_size,
        (unsigned) base_src_address,
        (unsigned) base_dest_address);

    const uint32_t alignment_mask = FAKE_FLASH_SECTOR_SIZE - 1;
    if (((src_size & alignment_mask) != 0)
    || ((base_src_address & alignment_mask) != 0)
    || ((dest_size & alignment_mask) != 0)
    || ((base_dest_address & alignment_mask) != 0)) {
        return PICO_ERROR_BAD_ALIGNMENT;
    }
    if ( !((base_src_address >= FAKE_FLASH_REUSABLE_START)
            && (base_src_address < limit_src_address)
            && (limit_src_address <= FAKE_FLASH_WIFI_SETTINGS_START)
            && (src_size == dest_size)
            && (base_dest_address >= FAKE_FLASH_PROGRAM_START)
            && (base_dest_address < limit_dest_address)
            && (limit_dest_address <= FAKE_FLASH_REUSABLE_START))) {
        return PICO_ERROR_INVALID_ADDRESS;
    }

    return PICO_ERROR_NONE;
}

int32_t wifi_settings_ota_firmware_update_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    ASSERT(input_data_size <= MAX_DATA_SIZE);
    ASSERT(*output_data_size == MAX_DATA_SIZE);
    *output_data_size = input_data_size;

    if ((input_data_size != sizeof(ota_firmware_update_parameter_t))
    || (input_parameter != 0)) {
        return PICO_ERROR_INVALID_ARG;
    }
    return check_ota_parameters(data_buffer, 1);
}

void wifi_settings_ota_firmware_update_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        void* arg) {

    ASSERT(input_data_size == sizeof(ota_firmware_update_parameter_t));
    if (input_parameter != 0) {
        printf("ota_firmware_update_handler: stage 2: input parameter %d != 0: do nothing\n",
            input_parameter);
        return;
    }

    int rc = check_ota_parameters(data_buffer, 2);
    if (rc != 0) {
        return;
    }
    ASSERT(input_parameter == 0);
    ota_firmware_update_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(ota_firmware_update_parameter_t));

    const uint32_t base_src_address = parameter.copy_from.start_address;
    const uint32_t src_size = parameter.copy_from.size;
    const uint32_t base_dest_address = parameter.copy_to.start_address;

    int fd = open("ota.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        lseek(fd, base_dest_address - FAKE_FLASH_PROGRAM_START, SEEK_SET);
        write(fd, &g_fake_flash[base_src_address - FAKE_FLASH_REUSABLE_START], src_size);
        close(fd);
    }
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

