/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test the connection
 */


#include "activity_connection_test.h"
#include "activity_ping.h"
#include "activity_dns_test.h"
#include "activity_telnet_test.h"
#include "user_interface.h"

#include "pico/stdlib.h"

typedef void (* callback_t) (void);

void activity_connection_test() {
    ui_clear();

    menu_t menu;
    ui_menu_init(&menu, MENU_FLAG_ENABLE_CANCEL);
    ui_menu_add_item(&menu, activity_ping, "Ping (test network connection)");
    ui_menu_add_item(&menu, activity_dns_test, "DNS (test name server connection)");
    ui_menu_add_item(&menu, activity_telnet_test, "Telnet (test TCP connection)");
    const int choice = ui_menu_show(&menu, NULL);
    const callback_t callback = ui_menu_get_arg(&menu, choice);
    if (callback) {
        callback();
    }
}
