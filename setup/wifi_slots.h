/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * wifi slots data structure (abstraction for ssid<N>=, pass<N>= etc.)
 */

#ifndef WIFI_SLOTS_H
#define WIFI_SLOTS_H

#include "file_operations.h"

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_configuration.h"

#include "pico/stdlib.h"

#define BSSID_AS_TEXT_CHARS             ((WIFI_BSSID_SIZE * 3) - 1)
#define BSSID_AS_TEXT_SIZE              (BSSID_AS_TEXT_CHARS + 2) // allow for two \0 bytes

typedef struct wifi_slot_item_t {
    int priority;
    int index_in_file;
    char ssid[WIFI_SSID_SIZE];
    char password[WIFI_PASSWORD_SIZE];
    bool is_bssid;
    bool is_open;
} wifi_slot_item_t;

typedef struct wifi_slot_data_t {
    wifi_slot_item_t item[MAX_NUM_SSIDS];
    int num_items;
} wifi_slot_data_t;

void wifi_slots_convert_string_to_bssid(const uint8_t* bssid, char* text);
void wifi_slots_renumber(wifi_slot_data_t* slot_data);
void wifi_slots_load(const file_handle_t* fh, wifi_slot_data_t* slot_data);
bool wifi_slots_save(file_handle_t* fh, const wifi_slot_data_t* slot_data);

#endif
