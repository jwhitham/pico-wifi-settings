/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test for wifi_settings_flash_storage_update.c
 *
 */

#include "unit_test.h"

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_flash_storage_update.h"
#include "wifi_settings/wifi_settings_flash_range.h"
#include "hardware/flash.h"
#include "pico/error.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MOCK_FILE_START_ADDRESS (PICO_FLASH_SIZE_BYTES - WIFI_SETTINGS_FILE_SIZE)
#define MOCK_FILE_END_ADDRESS (PICO_FLASH_SIZE_BYTES)


static uint flash_erase_count;
static uint flash_program_count;
static uint flash_verify_count;
static uint flash_program_error_at;
static char flash_fake[WIFI_SETTINGS_FILE_SIZE];
static uint int_disable_level;
static uint int_disable_count;

void reset_flash() {
    flash_erase_count = 0;
    flash_program_count = 0;
    flash_verify_count = 0;
    flash_program_error_at = WIFI_SETTINGS_FILE_SIZE + 100;
    memset(flash_fake, 0xcc, sizeof(flash_fake));
    int_disable_level = 0;
    int_disable_count = 0;
}

// Mock implementation of save_and_disable_interrupts
uint32_t save_and_disable_interrupts() {
    int_disable_level++;
    int_disable_count++;
    return 1234;
}

// Mock implementation of restore_interrupts 
void restore_interrupts(uint32_t flags) {
    ASSERT(flags == 1234);
    ASSERT(int_disable_level > 0);
    int_disable_level--;
}

// Mock implementation of flash_range_erase
void flash_range_erase(uint32_t flash_offs, size_t count) {
    flash_erase_count++;
    ASSERT(flash_offs == MOCK_FILE_START_ADDRESS);
    ASSERT(count == WIFI_SETTINGS_FILE_SIZE);
    ASSERT(int_disable_level > 0);
    memset(flash_fake, 0xff, sizeof(flash_fake));
}

// Mock implementation of flash_range_program
void flash_range_program(uint32_t flash_offs, const uint8_t *data, size_t count) {
    flash_program_count++;
    ASSERT(flash_offs >= MOCK_FILE_START_ADDRESS);
    ASSERT(flash_offs <= (MOCK_FILE_END_ADDRESS - FLASH_PAGE_SIZE));
    ASSERT(count == FLASH_PAGE_SIZE);
    ASSERT((flash_offs % FLASH_PAGE_SIZE) == 0);
    ASSERT(int_disable_level > 0);
    memcpy(&flash_fake[flash_offs - MOCK_FILE_START_ADDRESS],
            data, count);
}

// Mock implementation of wifi_settings_flash_range_verify
bool wifi_settings_flash_range_verify(
            const wifi_settings_flash_range_t* fr,
            const char* data) {
    const uint32_t flash_offs = fr->start_address;
    const uint32_t count = fr->size;
    flash_verify_count++;
    ASSERT(flash_offs >= MOCK_FILE_START_ADDRESS);
    ASSERT((flash_offs + count) <= MOCK_FILE_END_ADDRESS);
    ASSERT(int_disable_level == 0);
    ASSERT(count <= WIFI_SETTINGS_FILE_SIZE);
    if (flash_program_error_at < WIFI_SETTINGS_FILE_SIZE) {
        // Deliberate error introduced immediately before the first verify
        flash_fake[flash_program_error_at] ^= 1;
        flash_program_error_at = WIFI_SETTINGS_FILE_SIZE;
    }
    return memcmp(&flash_fake[flash_offs - MOCK_FILE_START_ADDRESS],
            data, count) == 0;
}

// Mock implementation of flash_safe_execute
int flash_safe_execute(void (*func)(void *), void *param, uint32_t) {
    func(param);
    return PICO_OK;
}

// Mock implementation of wifi_settings_range_get_wifi_settings_file
void wifi_settings_range_get_wifi_settings_file(wifi_settings_flash_range_t* r) {
    r->start_address = MOCK_FILE_START_ADDRESS;
    r->size = WIFI_SETTINGS_FILE_SIZE;
    wifi_settings_range_align_to_sector(r);
}

// Mock implementation of wifi_settings_range_align_to_sector
void wifi_settings_range_align_to_sector(wifi_settings_flash_range_t* r) {
    ASSERT(r->start_address == MOCK_FILE_START_ADDRESS);
    ASSERT(r->size == WIFI_SETTINGS_FILE_SIZE);
}

void test_wifi_settings_update_flash() {
    int ret = PICO_ERROR_GENERIC;

    char file[WIFI_SETTINGS_FILE_SIZE];
    memset(file, '\0', sizeof(file));

    const uint test_file_sizes[] = {13, FLASH_PAGE_SIZE - 1,
            FLASH_PAGE_SIZE, FLASH_PAGE_SIZE + 1,
            WIFI_SETTINGS_FILE_SIZE - FLASH_PAGE_SIZE - 13,
            WIFI_SETTINGS_FILE_SIZE - 13, WIFI_SETTINGS_FILE_SIZE - 1, WIFI_SETTINGS_FILE_SIZE, 0};
    for (uint i = 0; i < NUM_ELEMENTS(test_file_sizes); i++) {
        // GIVEN blank flash and files of various sizes containing test data
        reset_flash();
        for (uint j = 0; j < test_file_sizes[i]; j++) {
            file[j] = (char) (1 + i + j);
        }
        for (uint j = test_file_sizes[i]; j < WIFI_SETTINGS_FILE_SIZE; j++) {
            // This data should not be written
            file[j] = (char) (2 + i + j);
        }
        // WHEN flash is programmed
        ret = wifi_settings_update_flash_safe(file, test_file_sizes[i]);
        // THEN the flash programming process works correctly, with erase,
        // program and verify cycles, each with appropriate sizes and offsets,
        // and the programming correctly writes the data with correct padding
        fprintf(stderr, "i = %u ret = %d\n", i, ret);
        ASSERT(ret == PICO_OK);
        ASSERT(flash_erase_count == 1);
        ASSERT(int_disable_count > 0);
        ASSERT(int_disable_level == 0);
        uint num_blocks = (test_file_sizes[i] + FLASH_PAGE_SIZE - 1) / FLASH_PAGE_SIZE;
        ASSERT(flash_program_count == num_blocks);
        if (test_file_sizes[i] == WIFI_SETTINGS_FILE_SIZE) {
            ASSERT(flash_verify_count == 1); // no padding
        } else {
            ASSERT(flash_verify_count == 2); // verifies padding too
        }
        for (uint j = 0; j < test_file_sizes[i]; j++) {
            ASSERT(flash_fake[j] == file[j]);
        }
        for (uint j = test_file_sizes[i]; j < WIFI_SETTINGS_FILE_SIZE; j++) {
            ASSERT(flash_fake[j] == '\xff');
        }
    }

    const uint test_file_size = (FLASH_PAGE_SIZE * 3) / 2;
    const uint error_at[] = {0,     // error in first byte
            test_file_size - 1,     // error in final byte
            test_file_size};        // error in padding byte
    for (uint i = 0; i < NUM_ELEMENTS(error_at); i++) {
        // GIVEN blank flash and a file containing test data
        reset_flash();
        memset(file, '\n', sizeof(file));
        // WHEN flash is programmed but the programming fails
        flash_program_error_at = error_at[i];
        ret = wifi_settings_update_flash_safe(file, test_file_size);
        // THEN the flash verify step detects the error
        ASSERT(ret == PICO_ERROR_INVALID_DATA);
        ASSERT(flash_erase_count == 1);
        ASSERT(int_disable_count > 0);
        ASSERT(int_disable_level == 0);
        ASSERT(flash_program_count == 2);
        ASSERT(flash_verify_count != 0);
    }

    // GIVEN blank flash and a file containing test data
    reset_flash();
    // WHEN flash is programmed with a file size which is too large
    ret = wifi_settings_update_flash_safe(file, WIFI_SETTINGS_FILE_SIZE + 1);
    // THEN the flash function detects the error
    ASSERT(ret == PICO_ERROR_INVALID_ARG);
    ASSERT(flash_erase_count == 0);
    ASSERT(int_disable_count == 0);
    ASSERT(int_disable_level == 0);
    ASSERT(flash_program_count == 0);
    ASSERT(flash_verify_count == 0);
}

int main() {
    test_wifi_settings_update_flash();
    return 0;
}
