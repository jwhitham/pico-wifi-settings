/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Remote update service for wifi-settings. This defines built-in handlers
 * for reserved message types. These handlers are activated when
 * building with cmake -DWIFI_SETTINGS_REMOTE=2. They can read and write
 * arbitrary memory on the Pico and apply over-the-air (OTA) updates.
 */

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"
#include "wifi_settings/wifi_settings_remote_memory_access_handlers.h"
#include "wifi_settings/wifi_settings_flash_storage.h"
#include "wifi_settings/wifi_settings_flash_storage_update.h"

#include "hardware/flash.h"
#include "hardware/structs/sysinfo.h"
#include "hardware/structs/watchdog.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"
#include "hardware/xip_cache.h"

#include "pico/stdlib.h"
#include "pico/unique_id.h"
#include "pico/bootrom.h"

#if LIB_PICO_MULTICORE
#include "pico/multicore.h"
#endif

#include "mbedtls/sha256.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#ifndef ENABLE_REMOTE_MEMORY_ACCESS
#error "ENABLE_REMOTE_MEMORY_ACCESS must be enabled, i.e. cmake -DWIFI_SETTINGS_REMOTE=2"
#endif

#if MAX_DATA_SIZE < FLASH_SECTOR_SIZE
#error "MAX_DATA_SIZE must be >= FLASH_SECTOR_SIZE"
#endif


// End of usable Flash allows for the wifi-settings sector. This is a Flash address (0 = start of Flash).
#define FLASH_ADDRESS_END_OF_USABLE_FLASH (FLASH_ADDRESS_OF_WIFI_SETTINGS_FILE)

// Copy from flash.c
#define FLASH_BLOCK_ERASE_CMD 0xd8



// This handler can read from an arbitrary memory address.
// This implements the 'save' command.
// note: The source address is a logical address which can be anywhere in RAM.
// It may also be a Flash address.
// In the 0x10xxxxxx range, addresses may be translated to the current partition.
// In the 0x1cxxxxxx range (Pico 2), addresses are not translated.
int32_t wifi_settings_read_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    if ((input_data_size != sizeof(read_parameter_t)) || (input_parameter != 0)) {
        *output_data_size = 0;
        return PICO_ERROR_INVALID_ARG;
    }

    // Load the parameters
    read_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(read_parameter_t));

    if (parameter.copy_from.size > *output_data_size) {
        // Truncate requested size to fit the output buffer
        parameter.copy_from.size = *output_data_size;
    } else {
        // Truncate output size to fit the requested size
        *output_data_size = parameter.copy_from.size;
    }

    // Trying to read from an arbitrary address is dangerous. Some addresses
    // will cause a hard fault, i.e. crash the program. Let's try to be safe.
    // Is the requested address in Flash?
    wifi_settings_flash_range_t fr;
    if (wifi_settings_range_translate_to_flash(&parameter.copy_from, &fr)) {
        // Translated to a usable Flash address - translate back to logical range for copy
        wifi_settings_logical_range_t lr;
        wifi_settings_range_translate_to_logical(&fr, &lr);
        memcpy(data_buffer, lr.start_address, parameter.copy_from.size);
    } else {
        // Not translated to Flash... is it in SRAM?
        const uintptr_t start_address = (uintptr_t) parameter.copy_from.start_address;
        const uintptr_t end_address = start_address + parameter.copy_from.size;

        if ((start_address >= SRAM_BASE)
        && (start_address < end_address)
        && (end_address <= SRAM_END)) {
            memcpy(data_buffer, parameter.copy_from.start_address, parameter.copy_from.size);
        } else {
            // The address is not accessible
            *output_data_size = 0;
            return PICO_ERROR_INVALID_ADDRESS;
        } 
    }
    return (int32_t) parameter.copy_from.size;
}

typedef struct wifi_settings_write_flash_handler_params_t {
    wifi_settings_logical_range_t copy_from;
    wifi_settings_flash_range_t copy_to;
} wifi_settings_write_flash_handler_params_t;

static void wifi_settings_write_flash_handler_internal(void* tmp) {
    wifi_settings_write_flash_handler_params_t* param = (wifi_settings_write_flash_handler_params_t*) tmp;
    const uint32_t flags = save_and_disable_interrupts();
    flash_range_erase(param->copy_to.start_address, param->copy_to.size);
    flash_range_program(param->copy_to.start_address, param->copy_from.start_address,
                        param->copy_to.size);
    restore_interrupts(flags);
}

static int check_for_alignment_error(const wifi_settings_flash_range_t* fr) {
    // Make a copy of the range
    wifi_settings_flash_range_t fr2;
    memcpy(&fr2, fr, sizeof(wifi_settings_flash_range_t));

    // apply alignment function
    wifi_settings_range_align_to_sector(&fr2);

    // Any change is an error as the user should have provided aligned values
    if (fr2.start_address != fr->start_address) {
        return PICO_ERROR_BAD_ALIGNMENT;
    }
    if (fr2.size != fr->size) {
        return PICO_ERROR_INVALID_ARG;
    }
    return PICO_OK;
}

// This handler can write to a Flash sector. 
// This implements the 'load' command. The address must
// be appropriately aligned to an address in Flash and the input size must
// be a whole number of Flash sectors. There is an attempt to prevent the user overwriting
// the current program.
// note: The input_parameter (target address) is a Flash address (i.e. 0 = start of Flash)
int32_t wifi_settings_write_flash_handler(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    *output_data_size = 0;

    // This internal parameter structure is needed for use with flash_safe_execute
    wifi_settings_write_flash_handler_params_t param;
    param.copy_from.start_address = data_buffer;
    param.copy_from.size = input_data_size;
    param.copy_to.start_address = (uint32_t) input_parameter;
    param.copy_to.size = input_data_size;

    // Check alignment and size of the user's request
    int rc = check_for_alignment_error(&param.copy_to);
    if (rc != PICO_OK) {
        return rc;
    }

    // Check the target is within reusable Flash
    wifi_settings_flash_range_t reusable_flash;
    wifi_settings_range_get_reusable(&reusable_flash);
    if (!wifi_settings_range_is_contained(&param.copy_to, &reusable_flash)) {
        // Goes outside of usable Flash memory e.g. collides with current program,
        // wifi-settings file, or is just outside of the available space
        return PICO_ERROR_INVALID_ADDRESS;
    }

    // Looks good - rewrite sectors in Flash
    rc = flash_safe_execute(wifi_settings_write_flash_handler_internal,
                            &param, ENTER_EXIT_TIMEOUT_MS);
    if (rc != PICO_OK) {
        return rc;
    }
    // Test the results
    wifi_settings_logical_range_t lr;
    wifi_settings_range_translate_to_logical(&param.copy_to, &lr);
    if (memcmp(lr.start_address, param.copy_from.start_address, param.copy_from.size) != 0) {
        return PICO_ERROR_INVALID_DATA;
    }
    // Success
    return 0;
}

// Functions used by OTA updater
typedef struct ota_firmware_update_funcs_t {
    rom_connect_internal_flash_fn connect_internal_flash_func;
    rom_flash_exit_xip_fn flash_exit_xip_func;
    rom_flash_range_erase_fn flash_range_erase_func;
    rom_flash_flush_cache_fn flash_flush_cache_func;
    rom_flash_range_program_fn flash_range_program_func;
    rom_flash_enter_cmd_xip_fn flash_enter_cmd_xip_func;
} ota_firmware_update_funcs_t;

static bool setup_ota_firmware_update_funcs(ota_firmware_update_funcs_t* funcs) {
    funcs->connect_internal_flash_func = (rom_connect_internal_flash_fn)rom_func_lookup_inline(ROM_FUNC_CONNECT_INTERNAL_FLASH);
    funcs->flash_exit_xip_func = (rom_flash_exit_xip_fn)rom_func_lookup_inline(ROM_FUNC_FLASH_EXIT_XIP);
    funcs->flash_range_erase_func = (rom_flash_range_erase_fn)rom_func_lookup_inline(ROM_FUNC_FLASH_RANGE_ERASE);
    funcs->flash_flush_cache_func = (rom_flash_flush_cache_fn)rom_func_lookup_inline(ROM_FUNC_FLASH_FLUSH_CACHE);
    funcs->flash_range_program_func = (rom_flash_range_program_fn)rom_func_lookup_inline(ROM_FUNC_FLASH_RANGE_PROGRAM);
    funcs->flash_enter_cmd_xip_func = (rom_flash_enter_cmd_xip_fn)rom_func_lookup_inline(ROM_FUNC_FLASH_ENTER_CMD_XIP);
    return funcs->connect_internal_flash_func && funcs->flash_exit_xip_func
                && funcs->flash_range_erase_func && funcs->flash_flush_cache_func
                && funcs->flash_range_program_func && funcs->flash_enter_cmd_xip_func;
}

static void do_ota_firmware_update(
        ota_firmware_update_funcs_t* funcs,
        ota_firmware_update_parameter_t* parameter,
        uint32_t* data_buffer);

// This handler will verify an over-the-air (OTA) update without applying it.
int32_t wifi_settings_ota_firmware_update_handler1(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    *output_data_size = input_data_size;

    // Confirm that the parameters are correct
    if ((input_data_size != sizeof(ota_firmware_update_parameter_t))
    || (input_parameter != 0)) {
        return PICO_ERROR_INVALID_ARG;
    }
    // Check if it is possible to lock out the other core (if any)
    if (!wifi_settings_can_lock_out()) {
        return PICO_ERROR_NOT_PERMITTED;
    }
    // Check that all of the ROM functions needed for the firmware update are available
    ota_firmware_update_funcs_t funcs;
    if (!setup_ota_firmware_update_funcs(&funcs)) {
        return PICO_ERROR_UNSUPPORTED_MODIFICATION;
    }
    // Copy parameters for easier checking
    ota_firmware_update_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(ota_firmware_update_parameter_t));
    // Sizes must match
    if (parameter.copy_to.size != parameter.copy_from.size) {
        return PICO_ERROR_INVALID_ARG;
    }
    // Check alignment and size of both copy_from and copy_to
    int rc = check_for_alignment_error(&parameter.copy_from);
    if (rc != PICO_OK) {
        return rc;
    }
    rc = check_for_alignment_error(&parameter.copy_to);
    if (rc != PICO_OK) {
        return rc;
    }
    // Source must be within reusable Flash
    wifi_settings_flash_range_t reusable_flash;
    wifi_settings_range_get_reusable(&reusable_flash);
    if (!wifi_settings_range_is_contained(&parameter.copy_from, &reusable_flash)) {
        return PICO_ERROR_INVALID_ADDRESS;
    }
    // Target must be within Flash (it will overwrite the program,
    // so it doesn't have to be in reusable Flash)
    wifi_settings_flash_range_t all_flash;
    wifi_settings_range_get_all(&all_flash);
    if (!wifi_settings_range_is_contained(&parameter.copy_to, &all_flash)) {
        return PICO_ERROR_INVALID_ADDRESS;
    }
    // Target and source must not overlap
    if (wifi_settings_range_has_overlap(&parameter.copy_from, &parameter.copy_to)) {
        return PICO_ERROR_INVALID_ADDRESS;
    }
    // Target and wifi-settings file must not overlap
    wifi_settings_flash_range_t settings_file;
    wifi_settings_range_get_wifi_settings_file(&settings_file);
    if (wifi_settings_range_has_overlap(&settings_file, &parameter.copy_to)) {
        return PICO_ERROR_INVALID_ADDRESS;
    }
    // The addresses look good - what about the data itself? Check the hash.
    wifi_settings_logical_range_t copy_from_lr;
    wifi_settings_range_translate_to_logical(&parameter.copy_from, &copy_from_lr);
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    uint8_t digest_data[WIFI_SETTINGS_OTA_HASH_SIZE];

    if ((0 != mbedtls_sha256_starts_ret(&ctx, 0))
    || (0 != mbedtls_sha256_update_ret(&ctx, copy_from_lr.start_address, copy_from_lr.size))
    || (0 != mbedtls_sha256_finish_ret(&ctx, digest_data))) {
        return PICO_ERROR_GENERIC;
    }
    mbedtls_sha256_free(&ctx);

    if (memcmp(digest_data, parameter.hash, WIFI_SETTINGS_OTA_HASH_SIZE) != 0) {
        return PICO_ERROR_MODIFIED_DATA;
    }
    return 0;
}

// This handler will verify and then apply an over-the-air (OTA) update.
void wifi_settings_ota_firmware_update_handler2(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t callback1_data_size,
        int32_t callback1_parameter,
        void* arg) {

    // update was previously verified by handler1
    if (callback1_parameter != 0) {
        return; // should be unreachable (checked by handler1)
    }

    // load parameters (verified now)
    ota_firmware_update_parameter_t parameter;
    memcpy(&parameter, data_buffer, sizeof(ota_firmware_update_parameter_t));

    // load references to ROM functions
    ota_firmware_update_funcs_t funcs;
    if (!setup_ota_firmware_update_funcs(&funcs)) {
        return; // should be unreachable (checked by handler1)
    }

    // Going dark...
    if (!wifi_settings_do_lock_out()) {
        return;
    }

    // Watchdog functions are in Flash, so we can't call them as soon as we start erasing.
    // Solution is to enable the watchdog with a large timeout (1 second) and then reset
    // it periodically by writing directly to the register.
    watchdog_enable(1000, 1);

    // Run the rest of the process from RAM
    do_ota_firmware_update(&funcs, &parameter, (uint32_t*) data_buffer);
}

static void __no_inline_not_in_flash_func(do_ota_firmware_update)(
        ota_firmware_update_funcs_t* funcs,
        ota_firmware_update_parameter_t* parameter,
        uint32_t* copy_buffer) {

    // Continue the process started above (but running from RAM)
    wifi_settings_logical_range_t copy_from_lr;
    wifi_settings_range_translate_to_logical(&parameter->copy_from, &copy_from_lr);

    // Commit any pending writes to external RAM, to avoid losing them in the subsequent flush:
    xip_cache_clean_all();

    // No code will be executed from Flash from now on
    // (in fact we will never return to normal code execution - always reboot)
    __compiler_memory_barrier();

    // watchdog updates must now be done directly to the register
    volatile io_rw_32* watchdog_load = (io_rw_32*) (WATCHDOG_BASE + WATCHDOG_LOAD_OFFSET);

    // Do the copy; we cannot use memcpy, or any flash_range_* functions,
    // as all of them involve running some code from Flash, and we will
    // erase the program containing them. Everything must be in RAM or the boot ROM.
    // Connect the boot ROM functions here:
    funcs->connect_internal_flash_func();

    // Erase
    funcs->flash_exit_xip_func(); // read access to memory off
    for (uint32_t i = 0; i < parameter->copy_to.size; i += FLASH_SECTOR_SIZE) {
        *watchdog_load = 1000000;  // set to 500ms (RP2040) or 1 second (RP2350)
        funcs->flash_range_erase_func(
            i + parameter->copy_to.start_address,
            FLASH_SECTOR_SIZE, FLASH_BLOCK_SIZE, FLASH_BLOCK_ERASE_CMD);
    }
    funcs->flash_flush_cache_func();

    // Write
    for (uint32_t i = 0; i < parameter->copy_to.size; i += FLASH_SECTOR_SIZE) {
        *watchdog_load = 1000000;  // set to 500ms (RP2040) or 1 second (RP2350)

        // read data to be copied
        funcs->flash_enter_cmd_xip_func(); // read access to memory on
        const uint32_t* copy_from_ptr =
            (const uint32_t*) (((uintptr_t) copy_from_lr.start_address) + i);
        for (uint32_t j = 0; j < (FLASH_SECTOR_SIZE / 4); j++) {
            copy_buffer[j] = copy_from_ptr[j];
        }
        funcs->flash_exit_xip_func(); // read access to memory off

        funcs->flash_range_program_func(
            i + parameter->copy_to.start_address,
            (uint8_t*) copy_buffer, FLASH_SECTOR_SIZE);
        funcs->flash_flush_cache_func();
    }

    // Reboot
    *watchdog_load = 10;  // set to 5us (RP2040) or 10us (RP2350)
    while(1) {} // Wait for watchdog reset
}
