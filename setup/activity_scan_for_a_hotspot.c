/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Scan for a hotspot activity ("connection wizard")
 */

#include "activity_scan_for_a_hotspot.h"
#include "user_interface.h"
#include "file_operations.h"
#include "wifi_slots.h"

#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_configuration.h"

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "pico/bootrom.h"

#include <stdio.h>
#include <string.h>

#define MAX_WIFI_SCAN_RESULTS           MAX_MENU_ITEMS

typedef struct wifi_scan_data_item_t {
    cyw43_ev_scan_result_t raw;
    bool is_bssid;
    bool is_open;
} wifi_scan_data_item_t;

typedef struct wifi_scan_data_t {
    menu_t menu;
    wifi_scan_data_item_t item[MAX_WIFI_SCAN_RESULTS];
    int num_items;
    int actual_num_found;
} wifi_scan_data_t;

static int setup_wifi_scan_callback(void* arg, const cyw43_ev_scan_result_t* raw_result) {
    wifi_scan_data_t* scan_data = (wifi_scan_data_t*) arg;

    // Has this result already been seen?
    for (int i = 0; i < scan_data->num_items; i++) {
        if (memcmp(scan_data->item[i].raw.bssid, raw_result->bssid, WIFI_BSSID_SIZE) == 0) {
            // already seen
            return 0;
        }
    }

    // Record a new result
    scan_data->actual_num_found ++;
    if (scan_data->num_items >= MAX_WIFI_SCAN_RESULTS) {
        // No space for more results in the scan_data->item array
        return 0;
    }
    wifi_scan_data_item_t* item = &scan_data->item[scan_data->num_items];

    // Copy data from scan into the 'raw' field and examine it
    memcpy(&item->raw, raw_result, sizeof(cyw43_ev_scan_result_t));
    if ((item->raw.ssid_len == 0) || (item->raw.ssid_len >= WIFI_SSID_SIZE)) {
        // Invalid SSID - use BSSID only
        item->is_bssid = true;
    }
    item->is_open = (item->raw.auth_mode == CYW43_AUTH_OPEN);

    // Generate representation of BSSID
    char bssid_text[BSSID_AS_TEXT_SIZE];
    wifi_slots_convert_string_to_bssid(item->raw.bssid, bssid_text);

    // Create a description
    char description[MAX_DESCRIPTION_SIZE];
    memset(description, ' ', WIFI_SSID_SIZE);
    if (item->is_bssid) {
        const char* unnamed_text = "<unnamed>";
        memcpy(description, unnamed_text, strlen(unnamed_text));
    } else {
        memcpy(description, item->raw.ssid, item->raw.ssid_len);
    }
    snprintf(&description[WIFI_SSID_SIZE], MAX_DESCRIPTION_SIZE - WIFI_SSID_SIZE,
             " | %s | %3d | %d dB",
             bssid_text,
             (unsigned) item->raw.channel, (int) item->raw.rssi);

    // Add to menu if possible
    if (ui_menu_add_item(&scan_data->menu, item, "%s", description) < 0) {
        // No space for more results in scan_data->menu
        return 0;
    }
    scan_data->num_items++;
    return 0;
}

static void do_setup_wifi_scan(wifi_scan_data_t* scan_data) {
    printf("\nScanning: ");
    fflush(stdout);

    // Wait for any existing scan to finish (just in case wifi-settings was doing a scan)
    while (cyw43_wifi_scan_active(&cyw43_state)) {
        if (ui_waiting_check_abort()) {
            printf("\nError: interrupted while waiting for another scan to finish.\n");
            ui_wait_for_the_user();
            return;
        }
    }

    // start a scan here
    cyw43_wifi_scan_options_t opts;
    memset(&opts, 0, sizeof(opts));
    int rc = cyw43_wifi_scan(&cyw43_state, &opts, scan_data, setup_wifi_scan_callback);

    if (rc != PICO_OK) {
        printf("\nError: cyw43_wifi_scan returned error code %d\n", rc);
        ui_wait_for_the_user();
        return;
    }

    // wait for scan to finish (should only take a few seconds)
    while (cyw43_wifi_scan_active(&cyw43_state)) {
        if (ui_waiting_check_abort()) {
            printf("\nError: interrupted while waiting for scan results.\n");
            ui_wait_for_the_user();
            return;
        }
    }
    printf("\r");
}

void activity_scan_for_a_hotspot() {

    wifi_scan_data_t scan_data;
    wifi_slot_data_t slot_data;
    file_handle_t fh;

    // stop the wifi-settings library using the hardware
    wifi_settings_disconnect();

    // While user hasn't chosen a hotspot
    wifi_scan_data_item_t* item = NULL;
    while (!item) {
        ui_clear();

        // Reset all results
        memset(&scan_data, 0, sizeof(wifi_scan_data_t));
        ui_menu_init(&scan_data.menu, MENU_FLAG_ENABLE_RETRY | MENU_FLAG_ENABLE_CANCEL);

        // Load all data from the file
        file_load(&fh);

        // Load SSIDs from the file
        wifi_slots_load(&fh, &slot_data);

        if (slot_data.num_items >= NUM_SSIDS) {
            // File is full! Strictly speaking, if the file is full, the user could pick an existing ssid and update
            // the password, but it seems more helpful to tell the user that the file is full before scanning.
            printf("Unable to search.\n"
                   "There are no available SSID slots in the file, as ssid1 .. ssid%d\n"
                   "are all defined.\n"
                   "You need to delete one of the existing SSIDs in order to add another.\n"
                   "Use 'View and edit known hotspots' to delete a record.\n\n",
                   (int) NUM_SSIDS);
            ui_wait_for_the_user();
            return;
        }

        // Do the scan
        do_setup_wifi_scan(&scan_data);

        // Show a menu
        char caption[MAX_DESCRIPTION_SIZE];
        if (scan_data.num_items == 0) {
            snprintf(caption, sizeof(caption),
                "Sorry, no hotspots were found - please choose:\n");
        } else if (scan_data.actual_num_found != scan_data.num_items) {
            snprintf(caption, sizeof(caption),
                "Found %d, of which only %d can be shown, please choose:\n",
                scan_data.actual_num_found, scan_data.num_items);
        } else {
            snprintf(caption, sizeof(caption),
               "Found %d - please choose:\n", scan_data.num_items);
        }

        int choice = ui_menu_show(&scan_data.menu, caption);

        // if the choice is "cancel":
        if (choice == MENU_ITEM_CANCEL) {
            return; // give up
        }
        // if the choice is a hotspot, then item will be non-NULL, we leave the while loop
        // if the choice is "Refresh", then item == NULL, so the loop repeats
        item = (wifi_scan_data_item_t*) ui_menu_get_arg(&scan_data.menu, choice);
    }

    // Clear screen
    ui_clear();

    // Get the SSID name (or use BSSID)
    char ssid[WIFI_SSID_SIZE];
    if (item->is_bssid) {
        wifi_slots_convert_string_to_bssid(item->raw.bssid, ssid);
    } else {
        memcpy(ssid, item->raw.ssid, item->raw.ssid_len);
        ssid[(int)item->raw.ssid_len] = '\0';
    }

    // Is this SSID already known?
    int use_slot_index = slot_data.num_items;
    for (int slot_index = 0; slot_index < slot_data.num_items; slot_index++) {
        if ((item->is_bssid == slot_data.item[slot_index].is_bssid)
        && (strcmp(ssid, slot_data.item[slot_index].ssid) == 0)) {
            // matches
            use_slot_index = slot_index;
            break;
        }
    }

    // Prepare to ask for the password
    if (use_slot_index == slot_data.num_items) {
        // add new item
        slot_data.num_items++;
        slot_data.item[use_slot_index].priority = 0; // highest priority
        strcpy(slot_data.item[use_slot_index].ssid, ssid);
        strcpy(slot_data.item[use_slot_index].password, "");
        slot_data.item[use_slot_index].is_bssid = item->is_bssid;
        slot_data.item[use_slot_index].is_open = item->is_open;
    } else {
        // Load existing password
        printf("This SSID is already known, so the existing record will be updated");
    }

    // While not confirmed
    if (item->is_open) {
        printf("This is an open WiFi hotspot, so there is no password\n");
        strcpy(slot_data.item[use_slot_index].password, "");
    } else {
        if (!ui_ask_for_password(ssid, slot_data.item[use_slot_index].password)) {
            return; // Cancelled
        }
    }

    // Add to the file
    wifi_slots_renumber(&slot_data);
    wifi_slots_save(&fh, &slot_data);
    if (ui_file_save(&fh)) {
        // reconnect after adding the new hotspot
        wifi_settings_connect();
    }
}
