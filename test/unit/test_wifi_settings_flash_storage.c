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

static char file[WIFI_SETTINGS_FILE_SIZE + 2];

void test_wifi_settings_get_value_for_key() {
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
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
    ret = wifi_settings_get_value_for_key
        ("key", value, &value_size);
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
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
    ret = wifi_settings_get_value_for_key
        ("", value, &value_size);
    // THEN no value is found
    ASSERT(ret == false);
    ASSERT(value_size == sizeof(value));
    ASSERT(memcmp(value, unused, sizeof(value)) == 0);

    // GIVEN an oddly-formed value
    snprintf(file, sizeof(file), "k===v=\xa1u3 ");
    // WHEN trying to find the key
    value_size = sizeof(value);
    memcpy(value, unused, sizeof(value));
    ret = wifi_settings_get_value_for_key
        ("k", value, &value_size);
    // THEN the value is exactly whatever follows the first =
    ASSERT(ret == true);
    ASSERT(value_size == strlen(file) - 2);
    ASSERT(memcmp(value, &file[2], value_size) == 0);

    {
        // GIVEN a key that spans the whole file
        // (such that '=' appears at index WIFI_SETTINGS_FILE_SIZE)
        memset(file, 'k', sizeof(file));
        file[sizeof(file) - 2] = '=';
        file[sizeof(file) - 1] = '\0';
        // WHEN trying to find the key
        value_size = sizeof(value);
        memcpy(value, unused, sizeof(value));
        ret = wifi_settings_get_value_for_key
            (file, value, &value_size);
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
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
        ret = wifi_settings_get_value_for_key
            ("key", value, &value_size);
        // THEN nothing is found
        ASSERT(ret == false);
        ASSERT(value_size == sizeof(value));
        ASSERT(memcmp(value, unused, sizeof(value)) == 0);
    }

}

// Mock implementation of wifi_settings_range_get_wifi_settings_file
void wifi_settings_range_get_wifi_settings_file(wifi_settings_flash_range_t* r) {
    r->start_address = 0x1234;
    r->size = WIFI_SETTINGS_FILE_SIZE;
}

// Mock implementation of wifi_settings_range_translate_to_logical
void wifi_settings_range_translate_to_logical(
        const wifi_settings_flash_range_t* fr,
        wifi_settings_logical_range_t* lr) {
    ASSERT(fr->start_address == 0x1234);
    ASSERT(fr->size == WIFI_SETTINGS_FILE_SIZE);
    lr->start_address = file;
    lr->size = WIFI_SETTINGS_FILE_SIZE;
}



int main() {
    test_wifi_settings_get_value_for_key();
    return 0;
}
