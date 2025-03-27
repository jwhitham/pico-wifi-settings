/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * wifi-settings file operations
 */

#ifndef FILE_OPERATIONS_H
#define FILE_OPERATIONS_H

#include "wifi_settings/wifi_settings_configuration.h"

#include "pico/stdlib.h"

#include <stdbool.h>

typedef struct file_handle_t {
    char contents[WIFI_SETTINGS_FILE_SIZE];
} file_handle_t;

void file_load(file_handle_t* fh);
int file_save(const file_handle_t* fh);

void file_discard(file_handle_t* fh, const char* key);
bool file_set(file_handle_t* fh, const char* key, const char* value);
bool file_contains(const file_handle_t* fh, const char* key);
int file_get(const file_handle_t* fh, const char* key, char* value, const int value_size);
int file_get_next_key_value(
            const file_handle_t* fh, int* search_index,
            char *key, const int key_size,
            char *value, const int value_size);

#endif
