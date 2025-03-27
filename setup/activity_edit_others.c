/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Edit other fields in wifi-settings e.g. name, country, user-defined fields
 */

#include "activity_edit_others.h"
#include "activity_set_shared_secret.h"

#include "user_interface.h"
#include "file_operations.h"
#include "edit_key_value.h"

#include <stdio.h>
#include <string.h>

#define MAX_LINES_PER_PAGE      15
#define MAX_PAGES               100

typedef void (* callback_t) (void);

static bool accept_country_code(const char* unused, char* value) {
    if (strlen(value) != 2) {
        printf("The country code must be exactly two letters.\n");
        return false;
    }
    strupr(value);
    return true;
}

static bool edit_country_code(file_handle_t* fh) {
    return edit_key_value(fh, "country",
        "The country code should be a two-letter code from ISO-3166-1. See\n"
        "https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes for a list.\n"
        "This code is optional but a correct setting may improve WiFi performance.\n"
        "Please enter a country code or leave blank:\n",
        true, accept_country_code);
}

static void set_country_code() {
    file_handle_t fh;
    file_load(&fh);
    edit_country_code(&fh);
}

static bool edit_host_name(file_handle_t* fh) {
    return edit_key_value(fh, "name",
        "The Pico host name is used when connecting to a DHCP server. If the DHCP\n"
        "server is linked to a name server, e.g. dnsmasq, then it may be possible to\n"
        "use this name to connect to the Pico. The host name should conform to RFC 1034,\n"
        "see https://en.wikipedia.org/wiki/Hostname for more information.\n"
        "This field is optional. Please enter host name or leave blank:\n",
        true, NULL);
}

static void set_host_name() {
    file_handle_t fh;
    file_load(&fh);
    edit_host_name(&fh);
}

static bool edit_key_value_check_special(
            file_handle_t* fh,
            const char* key) {

    if (strcmp(key, "country") == 0) {
        return edit_country_code(fh);
    } else if (strcmp(key, "name") == 0) {
        return edit_host_name(fh);
    } else if (strcmp(key, "update_secret") == 0) {
        activity_set_shared_secret();
        return true;
    } else {
        return edit_key_value(fh, key, NULL, false, NULL);
    }
}

static void select_user_defined_keys() {
    file_handle_t fh;
    file_load(&fh);

    int page_start_index[MAX_PAGES];
    memset(page_start_index, 0, sizeof(page_start_index));

    int page_number = 0;

    while(true) {
        menu_t menu;
        ui_menu_init(&menu, MENU_FLAG_ENABLE_CANCEL);

        int search_index = page_start_index[page_number];
        bool is_final_page = ((page_number + 1) >= MAX_PAGES);
        char key[MAX_EDIT_LINE_LENGTH];
        char value[MAX_EDIT_LINE_LENGTH];

        for (int i = 0; i < MAX_LINES_PER_PAGE; i++) {
            int key_size = file_get_next_key_value(&fh, &search_index,
                    key, sizeof(key), value, sizeof(value));
            if (key_size <= 0) {
                is_final_page = true;
                break;
            }
            ui_menu_add_item(&menu, NULL, "Edit %s=%s", key, value);
        }
        if (!is_final_page) {
            page_start_index[page_number + 1] = search_index;
        }

        int none_of_these_index = ui_menu_add_item(&menu, NULL, "Add new key");
        int previous_index = MENU_ITEM_NOTHING;
        if (page_number > 0) {
            previous_index = ui_menu_add_item(&menu, NULL, "Previous page");
        }
        int next_index = MENU_ITEM_NOTHING;
        if (!is_final_page) {
            next_index = ui_menu_add_item(&menu, NULL, "Next page");
        }

        const int choice = ui_menu_show(&menu, NULL);
        if ((0 <= choice) && (choice < none_of_these_index)) {
            // find the key again
            search_index = page_start_index[page_number];
            for (int i = 0; i <= choice; i++) {
                file_get_next_key_value(&fh, &search_index,
                        key, sizeof(key), value, sizeof(value));
            }
            // open key/value editor
            if (!edit_key_value_check_special(&fh, key)) {
                return; // cancel
            }
        } else if (choice == none_of_these_index) {
            // Ask the user what key to edit
            printf("Please enter the key you wish to create or edit:\n");
            strcpy(key, "");
            if (!ui_text_entry(key, sizeof(key))) {
                return; // cancel
            }
            if (strlen(key) != 0) {
                if (!edit_key_value_check_special(&fh, key)) {
                    return; // cancel
                }
            }
        } else if (choice == previous_index) {
            if (page_number > 0) {
                page_number--;
            }
        } else if (choice == next_index) {
            if ((page_number + 1) < MAX_PAGES) {
                page_number++;
            }
        } else if (choice == MENU_ITEM_CANCEL) {
            return; // cancel
        }
    }
}



void activity_edit_others() {
    menu_t menu;
    ui_menu_init(&menu, MENU_FLAG_ENABLE_CANCEL);
    ui_menu_add_item(&menu, set_country_code, "Set country code");
    ui_menu_add_item(&menu, activity_set_shared_secret, "Set update_secret for remote updates");
    ui_menu_add_item(&menu, set_host_name, "Set host name");
    ui_menu_add_item(&menu, select_user_defined_keys, "View and edit user-defined keys");
    const int choice = ui_menu_show(&menu, NULL);
    const callback_t callback = ui_menu_get_arg(&menu, choice);
    if (callback) {
        callback();
    }
}
