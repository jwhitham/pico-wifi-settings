/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test for wifi_settings_flash_storage.c
 *
 */

#include "unit_test.h"

#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_flash_storage.h"
#include "wifi_settings/wifi_settings_flash_range.h"
#include "hardware/flash.h"
#include "pico/error.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MOCK_FILE_START_ADDRESS (PICO_FLASH_SIZE_BYTES - WIFI_SETTINGS_FILE_SIZE)
#define MOCK_FILE_END_ADDRESS (PICO_FLASH_SIZE_BYTES)


void test_wifi_settings_get_value_for_key_within_file() {
    char file[WIFI_SETTINGS_FILE_SIZE];
    char value[10];
    char unused[20];
    bool ret;
    uint value_size = sizeof(value);
    memset(unused, 0xcc, sizeof(unused));

    const char* key_value = "key=value";
    const uint key_position[] = {0, 1, 100, WIFI_SETTINGS_FILE_SIZE - strlen(key_value) - 1,
            WIFI_SETTINGS_FILE_SIZE - strlen(key_value)};
    for (uint i = 0; i < NUM_ELEMENTS(key_position); i++) {
        // GIVEN an otherwise blank file containing key=value in some position
        memset(file, '\n', sizeof(file));
        memcpy(&file[key_position[i]], key_value, strlen(key_value));
        // WHEN trying to find the key
        value_size = sizeof(value);
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN the key is found regardless of its position
        ASSERT(ret == true);
        ASSERT(value_size == 5);
        ASSERT(memcmp(value, "value", value_size) == 0);
    }
    for (uint i = 0; i < 5; i++) {
        // GIVEN an otherwise blank file containing key=value at the end, such
        // that part of the value is outside of the file (i.e. "key=valu", "key=val",
        // "key=va", "key=v", "key=")
        uint j = WIFI_SETTINGS_FILE_SIZE - 4 - i;
        memset(file, '\n', sizeof(file));
        memcpy(&file[j], key_value, WIFI_SETTINGS_FILE_SIZE - j);
        // WHEN trying to find the key
        value_size = sizeof(value);
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN only part of the value is found
        ASSERT(ret == true);
        ASSERT(value_size == i);
        ASSERT(memcmp(value, "value", value_size) == 0);
    }

    // GIVEN a file containing multiple keys including malformed ones
    snprintf(file, sizeof(file),
        " key=a\n"      // ignored because the key here is really " key"
        "key =b\n"      // ignored because the key here is really "key "
        "key\n"         // ignored because there is no '='
        "key=c\n"       // this is accepted
        "key=d\n");     // ignored because it follows the accepted key

    // WHEN trying to find the key
    value_size = sizeof(value);
    ret = wifi_settings_get_value_for_key_within_file
        (file, sizeof(file), "key", value, &value_size);
    // THEN only the correct value is found
    ASSERT(ret == true);
    ASSERT(value_size == 1);
    ASSERT(memcmp(value, "c", value_size) == 0);

    const char eof_type[] = "\x00\x1a\xff";
    for (uint i = 0; i < NUM_ELEMENTS(eof_type); i++) {
        // GIVEN a file where the true key is after an EOF character
        snprintf(file, sizeof(file),
            " key=a\n"      // ignored because the key here is really " key"
            "key =b\n"      // ignored because the key here is really "key "
            "key\n"         // ignored because there is no '='
            "%c"            // EOF character
            "key=c\n"       // ignored as it follows a character treated as EOF
            "key=d\n",      // ignored as it follows a character treated as EOF
            eof_type[i]);

        // WHEN trying to find the key
        value_size = sizeof(value);
        memcpy(value, unused, sizeof(value));
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN nothing is found
        ASSERT(ret == false);
        ASSERT(value_size == sizeof(value));
        ASSERT(memcmp(value, unused, sizeof(value)) == 0);
    }

    for (uint i = 0; i < NUM_ELEMENTS(eof_type); i++) {
        // GIVEN a file where the value is terminated by an EOF character rather than EOL
        snprintf(file, sizeof(file), "%s%c", key_value, eof_type[i]);

        // WHEN trying to find the key
        value_size = sizeof(value);
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN the value is correct
        ASSERT(ret == true);
        ASSERT(value_size == 5);
        ASSERT(memcmp(value, "value", value_size) == 0);
    }

    // GIVEN an empty key
    snprintf(file, sizeof(file), "=value\n");
    // WHEN trying to find the key
    value_size = sizeof(value);
    memcpy(value, unused, sizeof(value));
    ret = wifi_settings_get_value_for_key_within_file
        (file, sizeof(file), "", value, &value_size);
    // THEN no value is found
    ASSERT(ret == false);
    ASSERT(value_size == sizeof(value));
    ASSERT(memcmp(value, unused, sizeof(value)) == 0);

    // GIVEN an oddly-formed value
    snprintf(file, sizeof(file), "k===v=\xa1u3 ");
    // WHEN trying to find the key
    value_size = sizeof(value);
    memcpy(value, unused, sizeof(value));
    ret = wifi_settings_get_value_for_key_within_file
        (file, sizeof(file), "k", value, &value_size);
    // THEN the value is exactly whatever follows the first =
    ASSERT(ret == true);
    ASSERT(value_size == strlen(file) - 2);
    ASSERT(memcmp(value, &file[2], value_size) == 0);

    {
        uint small_file_size = sizeof(file) / 2;
        // GIVEN a key that spans the whole file
        memset(file, 'k', small_file_size);
        file[small_file_size] = '\0';
        // WHEN trying to find the key
        value_size = sizeof(value);
        memcpy(value, unused, sizeof(value));
        ret = wifi_settings_get_value_for_key_within_file
            (file, small_file_size, file, value, &value_size);
        // THEN no key is found
        ASSERT(ret == false);
        ASSERT(value_size == sizeof(value));
        ASSERT(memcmp(value, unused, value_size) == 0);
    }

    for (uint i = 0; i < 5; i++) {
        // GIVEN a value that's longer than the value size
        snprintf(file, sizeof(file), "%s", key_value);
        // WHEN trying to find the key
        value_size = i;
        memcpy(value, unused, sizeof(value));
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN the key is found and the value is truncated appropriately
        ASSERT(ret == true);
        ASSERT(value_size == i);
        ASSERT(memcmp(value, "value", value_size) == 0);
        ASSERT(value[i] == unused[0]);
    }

    const char blank_type[] = "\n\rk \xff";
    for (uint i = 0; i < NUM_ELEMENTS(blank_type); i++) {
        // GIVEN a blank file (filled with some blank character)
        memset(file, blank_type[i], sizeof(file));
        // WHEN trying to find a key
        value_size = sizeof(value);
        memcpy(value, unused, sizeof(value));
        ret = wifi_settings_get_value_for_key_within_file
            (file, sizeof(file), "key", value, &value_size);
        // THEN nothing is found
        ASSERT(ret == false);
        ASSERT(value_size == sizeof(value));
        ASSERT(memcmp(value, unused, sizeof(value)) == 0);
    }

}

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
    char file[WIFI_SETTINGS_FILE_SIZE];
    int ret = PICO_ERROR_GENERIC;

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
    test_wifi_settings_get_value_for_key_within_file();
    test_wifi_settings_update_flash();
    return 0;
}
