/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * User interface functions
 */

#include "user_interface.h"
#include "file_operations.h"
#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_connect.h"

#include "pico/stdlib.h"
#include "pico/bootrom.h"

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <ctype.h>



#define CONTROL_A           0x01
#define CONTROL_C           0x03
#define CONTROL_D           0x04
#define BACKSPACE           0x08
#define LF                  '\n'
#define CONTROL_L           0x0c
#define CR                  '\r'
#define CONTROL_Y           0x19
#define DEL                 0x7f

#ifndef WIFI_SETTINGS_VERSION_STRING
#error "WIFI_SETTINGS_VERSION_STRING should be set (in CMakeLists.txt)"
#endif
#ifndef DEMO_GIT_COMMIT
#error "DEMO_GIT_COMMIT should be set (in CMakeLists.txt)"
#endif

void ui_clear() {
    printf("\x1b[2J\rpico-wifi-settings setup app, version "
        WIFI_SETTINGS_VERSION_STRING "-" DEMO_GIT_COMMIT "\n");
    printf("This Pico has board id %s\n\n", wifi_settings_get_board_id_hex());
    fflush(stdout);
}

void ui_wait_for_the_user() {
    printf("Press Enter to continue:");
    fflush(stdout);
    while (true) {
        switch (getchar()) {
            case '\n':
            case '\r':
            case CONTROL_C:
            case CONTROL_D:
                printf("\n");
                return;
            default:
                break;
        }
    }
}

bool ui_choose_yes_or_no() {
    printf("Press 'y' for yes, 'n' for no:");
    fflush(stdout);
    while (true) {
        switch (getchar()) {
            case 'y':
            case 'Y':
                printf(" yes\n");
                return true;
            case 'n':
            case 'N':
            case CONTROL_C:
            case CONTROL_D:
                printf(" no\n");
                return false;
            default:
                break;
        }
    }
}

bool ui_text_entry(char* buffer, uint max_buffer_size) {
    uint position = strlen(buffer);
    bool refresh_flag = true;

    while (true) {
        // Refresh shows text that's already present
        if (refresh_flag) {
            printf("\r\x1b[0J\r    \r> %s", buffer);
            refresh_flag = false;
        }
        // Read input
        int ch = getchar();
        if ((ch >= 0x20)
        && (ch < 0x7f)
        && (position < (max_buffer_size - 1))) {
            // add ASCII character
            buffer[position] = ch;
            position++;
            buffer[position] = '\0';
            printf("%c", ch);
        }
        switch (ch) {
            case BACKSPACE:
            case DEL:
                if (position > 0) {
                    // remove character
                    position--;
                    buffer[position] = '\0';
                    printf("\x08 \x08");
                }
                break;
            case CONTROL_L:
                // refresh (control-L)
                refresh_flag = true;
                break;
            case CONTROL_A:
            case CONTROL_Y:
                // remove line (control-Y, control-A)
                position = 0;
                buffer[position] = '\0';
                refresh_flag = true;
                break;
            case CONTROL_C:
            case CONTROL_D:
                // cancel (control-C, control-D)
                position = 0;
                buffer[position] = '\0';
                printf("\n");
                return false;
            case CR:
            case LF:
                // accept (CR or LF)
                printf("\n");
                return true;
        }
    }
}

void ui_menu_init(menu_t* menu, uint flags) {
    memset(menu, 0, sizeof(menu_t));
    menu->flags = flags;
    menu->max_items = MAX_MENU_ITEMS;
    // reserve space for built-in options if enabled
    if (menu->flags & MENU_FLAG_ENABLE_CANCEL) {
        menu->max_items--;
    }
    if (menu->flags & MENU_FLAG_ENABLE_RETRY) {
        menu->max_items--;
    }
}

int ui_menu_add_item(menu_t* menu, void* arg, const char* format, ...) {
    if (menu->num_items >= menu->max_items) {
        // unable to add
        return MENU_ITEM_NO_MORE_SPACE;
    }

    va_list ap;
    va_start(ap, format);
    vsnprintf(menu->item[menu->num_items].description,
              MAX_DESCRIPTION_SIZE, format, ap);
    va_end(ap);
    menu->item[menu->num_items].arg = arg;
    menu->num_items++;
    return menu->num_items - 1;
}

void* ui_menu_get_arg(menu_t* menu, int index) {
    if ((index >= 0) && (index < menu->num_items)) {
        return menu->item[index].arg;
    }
    return NULL;
}


typedef struct status_summary_t {
    char connect_status[MAX_DESCRIPTION_SIZE];
    char ip_status[MAX_DESCRIPTION_SIZE];
} status_summary_t;

static void get_status(status_summary_t* s) {
    memset(s, 0, sizeof(status_summary_t));

    // get connection status
    wifi_settings_get_connect_status_text(s->connect_status, sizeof(s->connect_status));

    // Get current IP address, falling back to the hardware status if the address is not known
    if (!wifi_settings_get_ip_status_text(s->ip_status, sizeof(s->ip_status))) {
        wifi_settings_get_hw_status_text(s->ip_status, sizeof(s->ip_status));
    }
}

int ui_menu_show(menu_t* menu, const char* caption) {
    // Save counter (may change if built-in items were added)
    int user_num_items = menu->num_items;

    // add built-in options if enabled - for this we must increase the max number of items
    // since space was reserved for the built-in options
    int retry_option_index = -1;
    int cancel_option_index = -1;
    menu->max_items = MAX_MENU_ITEMS;
    if (menu->flags & MENU_FLAG_ENABLE_RETRY) {
        retry_option_index = ui_menu_add_item(menu, NULL, "Refresh");
    }
    if (menu->flags & MENU_FLAG_ENABLE_CANCEL) {
        cancel_option_index = ui_menu_add_item(menu, NULL, "Cancel");
    }

    int outcome = MENU_ITEM_REFRESH;
    while (outcome == MENU_ITEM_REFRESH) {
        ui_clear();

        // status is captured now
        status_summary_t status_summary;
        get_status(&status_summary);
        printf("%s\n%s\n\n", status_summary.connect_status, status_summary.ip_status);
        fflush(stdout);

        // Draw the menu
        if (caption == NULL) {
            printf("What would you like to do?\n");
        } else {
            printf("%s\n", caption);
        }
        int last_code = '\0';
        for (int i = 0; i < menu->num_items; i++) {
            fflush(stdout);
            last_code = i + '1'; // index 0 .. 8 appear as '1' .. '9'
            if (i >= 9) {
                last_code = i + 'a' - 9; // index 9, 10, etc. appear as 'a', 'b', ...
            }
            printf(" %c. %s\n", last_code, menu->item[i].description);
        }
        printf("Press '1' .. '%c' to select:", last_code);
        fflush(stdout);

        outcome = MENU_ITEM_NOTHING;
        while (outcome == MENU_ITEM_NOTHING) {
            int code = getchar_timeout_us(1000000);
            int choice = -1;
            if (('1' <= code) && (code <= '9')) {
                choice = code - '1'; // '1' .. '9' select index 0 .. 8
            } else if (('a' <= code) && (code <= 'z')) {
                choice = code + 9 - 'a'; // 'a', 'b' etc. select index 9, 10
            } else if (('A' <= code) && (code <= 'Z')) {
                choice = code + 9 - 'A'; // 'A', 'B' etc. also select index 9, 10
            } else if (code == CONTROL_C || code == CONTROL_D) {
                // control-C or control-D: cancel (always works even if there is no explicit cancel option)
                outcome = MENU_ITEM_CANCEL;
            } else if (code == CONTROL_L || code == CR) {
                // Refresh forced
                outcome = MENU_ITEM_REFRESH;
            } else if (code < 0) {
                // No key press, check for refresh
                // the menu will be refreshed whenever the status changes
                status_summary_t new_status_summary;
                get_status(&new_status_summary);
                if (memcmp(&status_summary, &new_status_summary, sizeof(status_summary_t)) != 0) {
                    outcome = MENU_ITEM_REFRESH;
                }
            }
            if ((0 <= choice) && (choice < menu->num_items)) {
                // valid selection
                printf(" %c", code);
                // check built-in options
                if (choice == cancel_option_index) {
                    outcome = MENU_ITEM_CANCEL;
                } else if (choice == retry_option_index) {
                    outcome = MENU_ITEM_RETRY;
                } else {
                    outcome = choice;
                }
            }
        }
        printf("\n");
    }

    // Restore counter (may have changed if built-in items were added)
    menu->num_items = user_num_items;
    return outcome;
}

bool ui_ask_for_password(const char* ssid, char* password) {
    // While we don't have a password, but a password is needed
    int password_size = 0;
    while (password_size == 0) {
        printf("\nPlease enter the password for '%s':\n", ssid);
        if (!ui_text_entry(password, WIFI_PASSWORD_SIZE)) {
            return false; // cancelled password entry - stop
        }
        password_size = (int) strlen(password);
        if (password_size < 8) {
            password_size = 0;
            printf("\nWiFi passwords must be at least 8 characters.\nTry again? ");
            if (!ui_choose_yes_or_no()) {
                return false; // give up
            }
        } else if (password_size >= (WIFI_PASSWORD_SIZE - 1)) {
            // 64 hex digits expected
            for (int i = 0; i < password_size; i++) {
                if (isxdigit((int) password[i])) {
                    password[i] = tolower(password[i]);
                } else {
                    password_size = 0;
                    printf("\nA %d-character password is treated as a key,\n"
                           "each character must be a hex digit. Try again? ",
                           WIFI_PASSWORD_SIZE - 1);
                    if (!ui_choose_yes_or_no()) {
                        return false; // give up
                    }
                }
            }
        }
    }
    // acceptable password
    return true;
}

bool ui_file_save(file_handle_t* fh) {
    printf("Saving:");
    fflush(stdout);
    int err = file_save(fh);
    if (err == PICO_ERROR_NONE) {
        printf(" ok\n");
        return true;
    }
    printf("\rError: save failed, error %d. "
           "Flash memory may not have been updated correctly\n", err);
    ui_wait_for_the_user();
    return false;
}

bool ui_waiting_check_abort() {
    printf(".");
    fflush(stdout);
    int code = getchar_timeout_us(250000);
    if (code == CONTROL_C || code == CONTROL_D) {
        // control-C or control-D: cancel
        return true;
    } else {
        return false;
    }
}


