/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * View/edit hotspots activity
 */

#include "activity_edit_hotspots.h"
#include "activity_scan_for_a_hotspot.h"
#include "user_interface.h"
#include "file_operations.h"
#include "wifi_slots.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>


typedef bool (* callback_t) (wifi_slot_data_t* slot_data, wifi_slot_item_t* item);

static bool set_ssid(wifi_slot_data_t*, wifi_slot_item_t* item) {
    printf("\nPlease edit the SSID:\n");
    return ui_text_entry(item->ssid, WIFI_SSID_SIZE);
}

static bool set_pass(wifi_slot_data_t*, wifi_slot_item_t* item) {
    item->is_open = false;
    return ui_ask_for_password(item->ssid, item->password);
}

static bool convert_to_open(wifi_slot_data_t*, wifi_slot_item_t* item) {
    item->is_open = true;
    strcpy(item->password, "");
    printf("\nThe password will be removed. Are you sure? ");
    return ui_choose_yes_or_no();
}

static bool set_prio(wifi_slot_data_t* slot_data, wifi_slot_item_t* item) {
    while (true) {
        printf("\nPlease edit the priority: range is 0 to %d\n"
               "If more than one known SSID is visible, then connection is attempted to\n"
                "the one with a smaller priority value first (i.e. ssid1 preferred to ssid2)\n",
               NUM_SSIDS + 1);
        char number[10];
        snprintf(number, sizeof(number), "%d", item->priority);
        if (!ui_text_entry(number, sizeof(number))) {
            return false; // cancelled priority entry - stop
        }

        char* end = number;
        int new_value = (int) strtol(number, &end, 0);
        if ((end[0] == '\0') && (number != end)
        && (new_value >= 0) && (new_value <= (NUM_SSIDS + 1))) {
            // The string is valid - set new priority
            item->priority = new_value;
            // Reorder the slots based on the new priority
            wifi_slots_renumber(slot_data);
            return true;
        } else {
            printf("\nThe priority value must be an integer in range 0 to %d.\nTry again? ", NUM_SSIDS + 1);
            if (!ui_choose_yes_or_no()) {
                return false; // give up
            }
        }
    }
}

static bool delete_ssid(wifi_slot_data_t* slot_data, wifi_slot_item_t* item) {
    printf("\nThe hotspot will be removed. Are you sure? ");
    if (!ui_choose_yes_or_no()) {
        return false; // stop
    }
    // Move this item to the end of the list then remove it
    item->priority = NUM_SSIDS + 1;
    wifi_slots_renumber(slot_data);
    slot_data->num_items--;
    return true;
}

void activity_edit_hotspots() {

    file_handle_t fh;
    wifi_slot_data_t slot_data;
    menu_t menu;
    // While user hasn't chosen a hotspot
    wifi_slot_item_t* item = NULL;
    while (!item) {
        // Load all data from the file
        file_load(&fh);

        // Load SSIDs from the file
        wifi_slots_load(&fh, &slot_data);

        if (slot_data.num_items == 0) {
            printf("The WiFi settings file has no hotspots defined!\n");
            printf("Would you like to scan for a hotspot? ");
            if (ui_choose_yes_or_no()) {
                activity_scan_for_a_hotspot();
            }
            return;
        }

        // Get status of each SSID
        ui_menu_init(&menu, MENU_FLAG_ENABLE_CANCEL | MENU_FLAG_ENABLE_RETRY);

        for (int slot_index = 0; slot_index < slot_data.num_items; slot_index++) {
            item = &slot_data.item[slot_index];
            const char* status = wifi_settings_get_ssid_status(item->index_in_file);

            ui_menu_add_item(&menu, item,
                "Edit %sssid%-2d | %-32s | last: %s",
                item->is_bssid ? "b" : " ", item->index_in_file,
                item->ssid, status);
        }

        // Ask the user which item they want to work on
        int choice = ui_menu_show(&menu, NULL);

        // if the choice is "cancel":
        if (choice == MENU_ITEM_CANCEL) {
            return; // give up
        }
        // if the choice is a hotspot, then item will be non-NULL, we leave the while loop
        // if Refresh, then item == NULL, so the loop repeats
        item = (wifi_slot_item_t *) ui_menu_get_arg(&menu, choice);
    }

    // Now ask the user what they would like to do with this hotspot
    ui_menu_init(&menu, MENU_FLAG_ENABLE_CANCEL);
    ui_menu_add_item(&menu, set_ssid, "Change the %sssid - currently %s", item->is_bssid ? "b" : "", item->ssid);
    ui_menu_add_item(&menu, set_pass, "%s password", item->is_open ? "Set a" : "Change the");
    if (!item->is_open) {
        ui_menu_add_item(&menu, convert_to_open, "Convert to open WiFi");
    }
    ui_menu_add_item(&menu, set_prio, "Change the priority - currently %d", item->priority);
    ui_menu_add_item(&menu, delete_ssid, "Delete %s", item->ssid);

    int choice = ui_menu_show(&menu, NULL);
    callback_t callback = ui_menu_get_arg(&menu, choice);
    if (callback && callback(&slot_data, item)) {
        // Write back
        wifi_slots_save(&fh, &slot_data);
        ui_file_save(&fh);
    }
}
