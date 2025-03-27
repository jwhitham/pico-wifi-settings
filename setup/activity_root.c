/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Root activity ("main menu")
 */

#include "activity_root.h"
#include "activity_scan_for_a_hotspot.h"
#include "activity_edit_hotspots.h"
#include "activity_connection_test.h"
#include "activity_force_disconnect_reconnect.h"
#include "activity_set_shared_secret.h"
#include "activity_edit_others.h"
#include "user_interface.h"

#include "wifi_settings.h"

#include "pico/bootrom.h"
#include "user_interface.h"

#include <stdio.h>

typedef void (* callback_t) (void);

static void reboot_callback() {
    printf("This Pico will now return to the bootloader. Goodbye!\n");
    fflush(stdout);
    reset_usb_boot(0, 0);
}

void activity_root() {

    const int init_rc = wifi_settings_init();
    wifi_settings_connect();
    ui_clear();

    int choice = 0;
    menu_t menu;

    while (choice != MENU_ITEM_CANCEL) {
        ui_menu_init(&menu, 0);
        if (init_rc == 0) {
            ui_menu_add_item(&menu, activity_scan_for_a_hotspot, "Scan for a new hotspot");
            if (!wifi_settings_has_no_wifi_details()) {
                ui_menu_add_item(&menu, activity_edit_hotspots, "View and edit known hotspots");
                ui_menu_add_item(&menu, activity_connection_test, "Perform connection test");
                ui_menu_add_item(&menu, activity_force_disconnect_reconnect, "Force disconnect/reconnect");
                ui_menu_add_item(&menu, activity_set_shared_secret, "Set update_secret for remote updates");
                ui_menu_add_item(&menu, activity_edit_others, "Edit other items in the wifi-settings file");
            }
        }
        ui_menu_add_item(&menu, reboot_callback, "Reboot (return to bootloader)");
        choice = ui_menu_show(&menu, NULL);
        callback_t callback = ui_menu_get_arg(&menu, choice);
        if (callback) {
            callback();
        }
    }
    reboot_callback();
}
