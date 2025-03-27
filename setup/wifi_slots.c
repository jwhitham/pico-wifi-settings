/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * wifi slots data structure (abstraction for ssid<N>=, pass<N>= etc.)
 */

#include "wifi_slots.h"
#include "file_operations.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>


#define SEARCH_KEY_SIZE                 20

static void generate_bssid_search_key(char* key, int index) {
    snprintf(key, SEARCH_KEY_SIZE, "bssid%d", index);
}

static void generate_ssid_search_key(char* key, int index) {
    snprintf(key, SEARCH_KEY_SIZE, "ssid%d", index);
}

static void generate_pass_search_key(char* key, int index) {
    snprintf(key, SEARCH_KEY_SIZE, "pass%d", index);
}

void wifi_slots_convert_string_to_bssid(const uint8_t* bssid, char* text) {
    // A BSSID is represented as 01:23:45:67:89:ab
    for (int i = 0; i < WIFI_BSSID_SIZE; i++) {
        snprintf(&text[i * 3], 4, "%02x:", bssid[i]);
    }
    // remove final ':'
    text[BSSID_AS_TEXT_CHARS] = '\0';
}

void wifi_slots_load(const file_handle_t* fh, wifi_slot_data_t* slot_data) {
    // Load SSIDs from file, copy them to an array of items
    memset(slot_data, 0, sizeof(wifi_slot_data_t));

    for (int index_in_file = 1; index_in_file <= NUM_SSIDS; index_in_file++) {
        // Here is the array index that we will populate if possible
        const int index_in_array = slot_data->num_items;
        bool is_used = false;

        // Check for a BSSID or SSID value here and load it
        char key[SEARCH_KEY_SIZE];
        generate_bssid_search_key(key, index_in_file);
        int size = file_get(fh, key, slot_data->item[index_in_array].ssid, WIFI_SSID_SIZE - 1);
        if (size > 0) {
            is_used = true;
            slot_data->item[index_in_array].is_bssid = true;
            slot_data->item[index_in_array].ssid[size] = '\0';
        } else {
            generate_ssid_search_key(key, index_in_file);
            size = file_get(fh, key, slot_data->item[index_in_array].ssid, WIFI_SSID_SIZE - 1);
            if (size > 0) {
                is_used = true;
                slot_data->item[index_in_array].ssid[size] = '\0';
            }
        }

        // If there is an SSID/BSSID..
        if (is_used) {
            // keep this record:
            slot_data->num_items++;
            // set index and priority to match the current index
            slot_data->item[index_in_array].priority = index_in_file;
            slot_data->item[index_in_array].index_in_file = index_in_file;
            // and then look for a password
            generate_pass_search_key(key, index_in_file);
            size = file_get(fh, key, slot_data->item[index_in_array].password, WIFI_PASSWORD_SIZE - 1);
            if (size <= 0) {
                slot_data->item[index_in_array].is_open = true;
            } else {
                slot_data->item[index_in_array].password[size] = '\0';
            }
        }
    }
}

static int compare_slot_items(const void* p1, const void* p2) {
    const wifi_slot_item_t* i1 = (const wifi_slot_item_t*) p1;
    const wifi_slot_item_t* i2 = (const wifi_slot_item_t*) p2;
    int cmp = i1->priority - i2->priority;
    if (cmp == 0) {
        // Original index in the file is a tie-breaker
        cmp = i1->index_in_file - i2->index_in_file;
    }
    return cmp;
}

void wifi_slots_renumber(wifi_slot_data_t* slot_data) {
    qsort(slot_data->item, slot_data->num_items, sizeof(wifi_slot_item_t), compare_slot_items);
}

void wifi_slots_save(file_handle_t* fh, const wifi_slot_data_t* slot_data) {
    // add updated wifi slots
    for (int index_in_array = 0; index_in_array < slot_data->num_items; index_in_array++) {
        const int index_in_file = index_in_array + 1;
        char key[SEARCH_KEY_SIZE];

        // Password first (prepending)
        if (!slot_data->item[index_in_array].is_open) {
            generate_pass_search_key(key, index_in_file);
            file_set(fh, key, slot_data->item[index_in_array].password);
        }
        // SSID or BSSID
        if (slot_data->item[index_in_array].is_bssid) {
            // BSSID - first discard SSID
            generate_ssid_search_key(key, index_in_file);
            file_discard(fh, key);
            generate_bssid_search_key(key, index_in_file);
        } else {
            // SSID - first discard BSSID
            generate_bssid_search_key(key, index_in_file);
            file_discard(fh, key);
            generate_ssid_search_key(key, index_in_file);
        }
        file_set(fh, key, slot_data->item[index_in_array].ssid);
    }
    // discard any other wifi slots from the file
    for (int index_in_file = slot_data->num_items + 1; index_in_file <= NUM_SSIDS; index_in_file++) {
        char key[SEARCH_KEY_SIZE];
        generate_bssid_search_key(key, index_in_file);
        file_discard(fh, key);
        generate_ssid_search_key(key, index_in_file);
        file_discard(fh, key);
        generate_pass_search_key(key, index_in_file);
        file_discard(fh, key);
    }

}
