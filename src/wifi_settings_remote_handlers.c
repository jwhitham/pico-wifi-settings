/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Remote update service for wifi-settings. This defines built-in handlers
 * for reserved message types. These handlers are activated when
 * building with cmake -DWIFI_SETTINGS_REMOTE=1 or -DWIFI_SETTINGS_REMOTE=2.
 */

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"
#include "wifi_settings/wifi_settings_flash_range.h"

#include "hardware/flash.h"
#include "hardware/structs/sysinfo.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"

#include "pico/binary_info/structure.h"
#include "pico/stdlib.h"
#include "pico/bootrom.h"
#include "pico/cyw43_arch.h"

#if LIB_PICO_MULTICORE
#include "pico/multicore.h"
#endif

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled, i.e. cmake -DWIFI_SETTINGS_REMOTE=1"
#endif
#ifndef WIFI_SETTINGS_VERSION_STRING
#error "WIFI_SETTINGS_VERSION_STRING must be set"
#endif

// Marks the binary info section
extern binary_info_t* __binary_info_start[];
extern binary_info_t* __binary_info_end[];

static const char* binary_info_get_string_for_id(uint32_t id) {
    for (binary_info_t** item = __binary_info_start;
                item != __binary_info_end; item++) {
        if ((item[0]->type == BINARY_INFO_TYPE_ID_AND_STRING)
        && (item[0]->tag == BINARY_INFO_TAG_RASPBERRY_PI)) {
            binary_info_id_and_string_t* id_and_string_item =
                (binary_info_id_and_string_t*) item[0];
            if (id_and_string_item->id == id) {
                return id_and_string_item->value;
            }
        }
    }
    return NULL;
}

typedef struct pico_info_buf_t {
    char* text;
    uint index;
    uint max_text_size;
} pico_info_buf_t;

static void add_pico_info_string(
        pico_info_buf_t* buf,
        const char* key,
        const char* value) {
    if (!value) {
        return;
    }
    const uint value_size = strlen(value);
    if (!value_size) {
        return;
    }
    const uint key_size = strlen(key);
    const uint total_size = key_size + value_size + 2;
    if ((total_size + buf->index) > buf->max_text_size) {
        return;
    }
    strcpy(&buf->text[buf->index], key);
    buf->index += key_size;
    strcpy(&buf->text[buf->index], "=");
    buf->index ++;
    strcpy(&buf->text[buf->index], value);
    buf->index += value_size;
    strcpy(&buf->text[buf->index], "\n");
    buf->index ++;
}

static void add_pico_info_u32(
        pico_info_buf_t* buf,
        const char* key,
        uint32_t value) {
    char tmp_buf[16];
    snprintf(tmp_buf, sizeof(tmp_buf), "0x%08x", (unsigned) value);
    add_pico_info_string(buf, key, tmp_buf);
}

static void add_pico_info_range(
        pico_info_buf_t* buf,
        const char* key,
        void (* range_callback) (wifi_settings_flash_range_t* fr)) {

    wifi_settings_flash_range_t fr;
    range_callback(&fr);

    char tmp_buf[32];
    snprintf(tmp_buf, sizeof(tmp_buf), "0x%08x:0x%08x",
        (unsigned) fr.start_address, (unsigned) (fr.start_address + fr.size));
    add_pico_info_string(buf, key, tmp_buf);
}

int32_t wifi_settings_pico_info_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    // No input is accepted
    if ((input_data_size != 0) || (input_parameter != 0)) {
        *output_data_size = 0;
        return PICO_ERROR_INVALID_ARG;
    }

    // Set up for copying info text
    pico_info_buf_t buf;
    memset(data_buffer, 0, *output_data_size);
    buf.text = (char*) data_buffer;
    buf.index = 0;
    buf.max_text_size = *output_data_size;

    // data to help with reprogramming
    add_pico_info_u32(&buf, "flash_sector_size", FLASH_SECTOR_SIZE);
    add_pico_info_u32(&buf, "max_data_size", *output_data_size);
    add_pico_info_range(&buf, "flash_all", wifi_settings_range_get_all);
    add_pico_info_range(&buf, "flash_reusable", wifi_settings_range_get_reusable);
    add_pico_info_range(&buf, "flash_wifi_settings_file", wifi_settings_range_get_wifi_settings_file);
    add_pico_info_range(&buf, "flash_program", wifi_settings_range_get_program);

    // get logical memory offset for untranslated read accesses to Flash
    // (this address represents the start of Flash memory, i.e. flash address 0)
    wifi_settings_flash_range_t fr;
    wifi_settings_logical_range_t lr;
    wifi_settings_range_get_all(&fr);
    wifi_settings_range_translate_to_logical(&fr, &lr);
    add_pico_info_u32(&buf, "logical_offset", (uint32_t) ((uintptr_t) lr.start_address));

    // relevant features enabled
#if LIB_PICO_MULTICORE
    add_pico_info_string(&buf, "multicore", "1");
#endif
#ifdef ENABLE_REMOTE_MEMORY_ACCESS
    add_pico_info_string(&buf, "remote_memory_access", "1");
#endif

    // sysinfo chip ID from sysinfo registers
    add_pico_info_u32(&buf, "sysinfo_chip_id", *((io_ro_32*)(SYSINFO_BASE + SYSINFO_CHIP_ID_OFFSET)));

    // board id
    add_pico_info_string(&buf, "board_id", wifi_settings_get_board_id_hex());

    // network info
    add_pico_info_string(&buf, "name", wifi_settings_get_hostname());
    char tmp_buf[16];
    add_pico_info_string(&buf, "ip",
        netif_default ? ip4addr_ntoa_r(netif_ip4_addr(netif_default),
                               tmp_buf, sizeof(tmp_buf)) : NULL);

    // program info
    add_pico_info_string(&buf, "wifi_settings_version", WIFI_SETTINGS_VERSION_STRING);
    add_pico_info_string(&buf, "program",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_NAME));
    add_pico_info_string(&buf, "version",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_VERSION_STRING));
    add_pico_info_string(&buf, "build_date",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_BUILD_DATE_STRING));
    add_pico_info_string(&buf, "url",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_URL));
    add_pico_info_string(&buf, "description",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_DESCRIPTION));
    add_pico_info_string(&buf, "feature",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_FEATURE));
    add_pico_info_string(&buf, "build_attribute",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_PROGRAM_BUILD_ATTRIBUTE));
    add_pico_info_string(&buf, "sdk_version",
        binary_info_get_string_for_id(BINARY_INFO_ID_RP_SDK_VERSION));
    *output_data_size = buf.index;
    return 0;
}

int32_t wifi_settings_update_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    *output_data_size = 0;
    if (input_parameter != 0) {
        return PICO_ERROR_INVALID_ARG;
    }
    int rc = wifi_settings_update_flash_safe((const char*) data_buffer, input_data_size);
    if (rc != PICO_OK) {
        return rc;
    }

    wifi_settings_remote_update_secret();
    wifi_settings_set_hostname();
    return (int32_t) input_data_size;
}

// For ID_UPDATE_REBOOT_HANDLER (second stage)
// No first stage is required here, as the input is always valid; not providing a first stage
// will just cause the user-provided input_data_size and input_parameter to be passed through.
void wifi_settings_update_reboot_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t callback1_data_size,
        int32_t callback1_parameter,
        void* arg) {

    save_and_disable_interrupts(); // Stop core 0 responding
#if LIB_PICO_MULTICORE
    multicore_reset_core1(); // Stop core 1
#endif

    if (callback1_data_size != 0) {
        // update
        wifi_settings_update_flash_unsafe((const char*) data_buffer, (uint) callback1_data_size);
    }
#ifdef ENABLE_REMOTE_MEMORY_ACCESS
    if (callback1_parameter == 1) {
        // go to the bootloader instead of rebooting into user firmware
        reset_usb_boot(0, 0);
    }
#endif
    watchdog_enable(1, 1);  // Watchdog triggered in 1ms
    while(1) {} // Wait for watchdog reset
}
