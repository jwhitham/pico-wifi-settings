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
#include "file_finder.h"

#include "pico/stdlib.h"
#include "pico/binary_info.h"

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <ctype.h>
#include <limits.h>



#define CONTROL_A           0x01
#define CONTROL_C           0x03
#define CONTROL_D           0x04
#define BACKSPACE           0x08
#define LF                  '\n'
#define CONTROL_L           0x0c
#define CR                  '\r'
#define CONTROL_Y           0x19
#define ESC_BYTE            0x1b
#define KEY_UP              0x100
#define KEY_DOWN            0x101
#define KEY_LEFT            0x102
#define KEY_RIGHT           0x103
#define DEL                 0x7f

#define MENU_CAPTION_LINE       7
#define MENU_ITEMS_PER_PAGE     12
#define MENU_FOOTER_LINE        (MENU_CAPTION_LINE + 2 + MENU_ITEMS_PER_PAGE)

#define ANSI_CLEAR_SCREEN   "\x1b[2J"
#define ANSI_CLEAR_LINE     "\x1b[0J"
#define ANSI_BOLD_FONT      "\x1b[1m"
#define ANSI_NORMAL_FONT    "\x1b[0m"

#ifndef WIFI_SETTINGS_VERSION_STRING
#error "WIFI_SETTINGS_VERSION_STRING should be set (in CMakeLists.txt)"
#endif
#ifndef SETUP_GIT_COMMIT
#error "SETUP_GIT_COMMIT should be set (in CMakeLists.txt)"
#endif


typedef enum {
    NO_ESCAPE = 0,
    FE_ESCAPE_CODE,     // received "\x1b"
    CSI_ESCAPE_CODE,    // received "\x1b["
} escape_state_t;

static escape_state_t g_escape_state = NO_ESCAPE;

static void cursor_go_to_line(const int line_number) {
    // ANSI code to go to a particular line
    printf("\x1b[%dH\r", line_number + 1);
}

void ui_clear() {
    printf(ANSI_CLEAR_SCREEN);
    cursor_go_to_line(0);
    printf(ANSI_BOLD_FONT
        "\rpico-wifi-settings setup app, version "
        WIFI_SETTINGS_VERSION_STRING "-" SETUP_GIT_COMMIT
        ANSI_NORMAL_FONT "\n\n");
    fflush(stdout);
    // Some binary info is set in CMakeLists but it is easier to set these here with
    // the #defines available
    bi_decl_if_func_used(bi_program_version_string(
        WIFI_SETTINGS_VERSION_STRING "-" SETUP_GIT_COMMIT));
    bi_decl_if_func_used(bi_program_url(WIFI_SETTINGS_PROJECT_URL));
    bi_decl_if_func_used(bi_program_description(
        "Interactive text-mode application for configuring WiFi settings, "
        "testing them and storing them in Flash"));
}

int ui_getchar_timeout_us(uint32_t timeout_us) {
    int ch;
    while (true) {
        ch = getchar_timeout_us(timeout_us);
        if (ch < 0) {
            return ch;
        }
        switch (g_escape_state) {
            case NO_ESCAPE:
                if (ch == ESC_BYTE) {
                    g_escape_state = FE_ESCAPE_CODE;
                } else {
                    return ch;
                }
                break;
            case FE_ESCAPE_CODE:
                if (ch == '[') {
                    g_escape_state = CSI_ESCAPE_CODE;
                } else {
                    g_escape_state = NO_ESCAPE;
                }
                break;
            case CSI_ESCAPE_CODE:
                if ((ch >= 0x20) && (ch <= 0x3e)) {
                    // parameter byte or intermediate byte - continue escape
                } else {
                    // final byte or undefined byte - escape sequence ends
                    g_escape_state = NO_ESCAPE;
                    switch (ch) {
                        case 'A': return KEY_UP;
                        case 'B': return KEY_DOWN;
                        case 'C': return KEY_RIGHT;
                        case 'D': return KEY_LEFT;
                        default: break;
                    }
                }
                break;
        }
    }
}

int ui_getchar() {
    int ch;
    do {
        ch = ui_getchar_timeout_us(UINT_MAX);
    } while (ch < 0);
    return ch;
}

void ui_wait_for_the_user() {
    printf("Press Enter to continue:");
    fflush(stdout);
    while (true) {
        switch (ui_getchar()) {
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
        switch (ui_getchar()) {
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
            printf("\r" ANSI_CLEAR_LINE "\r    \r> %s", buffer);
            refresh_flag = false;
        }
        // Read input
        int ch = ui_getchar();
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
    char settings_file_status[MAX_DESCRIPTION_SIZE];
    char connect_status[MAX_DESCRIPTION_SIZE];
    char ip_status[MAX_DESCRIPTION_SIZE];
} status_summary_t;

static void get_status(status_summary_t* s) {
    memset(s, 0, sizeof(status_summary_t));

    // Get settings file info
    file_finder_get_status_text(s->settings_file_status, sizeof(s->settings_file_status));

    // Get connection status
    wifi_settings_get_connect_status_text(s->connect_status, sizeof(s->connect_status));

    // Get current IP address, falling back to the hardware status if the address is not known
    if (!wifi_settings_get_ip_status_text(s->ip_status, sizeof(s->ip_status))) {
        wifi_settings_get_hw_status_text(s->ip_status, sizeof(s->ip_status));
    }
}

static int get_code_for_item(const int item_index, const int page_start_index) {
    const int offset = item_index - page_start_index;
    if (offset < 0) {
        // Not visible on this page
        return -1;
    } else if (offset < 9) {
        // First 9 items have value '1' .. '9'
        return '1' + offset;
    } else if (offset < MENU_ITEMS_PER_PAGE) {
        // Remaining items have letter codes
        return 'a' + offset - 9;
    } else {
        // Not visible on this page
        return -1;
    }
}

static void draw_menu_item(const menu_t* menu,
                        const int item_index,
                        const int cursor_index,
                        const int page_start_index) {
    // Defensively skip any out-of-range item
    if ((item_index < 0) || (item_index >= menu->num_items)) {
        return;
    }
    // Defensively skip items that don't appear on this page (code will be -1)
    const int code = get_code_for_item(item_index, page_start_index);
    if (code < 0) {
        return;
    }
    // Draw this item
    cursor_go_to_line(MENU_CAPTION_LINE + item_index - page_start_index);
    if (cursor_index == item_index) {
        // Turn on bold font
        printf("\n" ANSI_BOLD_FONT "\r >> ");
    } else {
        printf("\n %c. ", code);
    }
    printf("%s", menu->item[item_index].description);
    if (cursor_index == item_index) {
        // Turn off bold font
        printf(ANSI_NORMAL_FONT "\r");
    }
}

static void draw_menu_footer(const int page_start_index,
                        const int page_end_index,
                        const int num_items) {
    cursor_go_to_line(MENU_FOOTER_LINE);
    printf("Press '%c' .. '%c' to select",
            get_code_for_item(page_start_index, page_start_index),
            get_code_for_item(page_end_index - 1, page_start_index));
    if (page_start_index > 0) {
        printf(", 'p' for previous page");
    }
    if (page_end_index < num_items) {
        printf(", 'n' for next page");
    }
    printf(":");
    fflush(stdout);
}

int ui_menu_show(menu_t* menu, const char* caption) {
    // Save counter (may change if built-in items were added)
    const int user_num_items = menu->num_items;

    // add built-in options if enabled - for this we must increase the max number of items
    // since space was reserved for the built-in options
    menu->max_items = MAX_MENU_ITEMS;
    const int retry_option_index = 
        (menu->flags & MENU_FLAG_ENABLE_RETRY) ?
            ui_menu_add_item(menu, NULL, "Refresh") : -1;
    const int cancel_option_index =
        (menu->flags & MENU_FLAG_ENABLE_CANCEL) ?
            ui_menu_add_item(menu, NULL, "Cancel") : -1;

    // Default caption
    if (caption == NULL) {
        caption = "What would you like to do?";
    }

    // How many pages?
    const int num_pages = (menu->num_items + MENU_ITEMS_PER_PAGE - 1) / MENU_ITEMS_PER_PAGE;

    // Current editing status
    int current_page_number = 0;
    int outcome = MENU_ITEM_REFRESH;
    int current_cursor_index = -1;

    // capture current board status
    status_summary_t status_summary;
    get_status(&status_summary);

    // Outer loop redraws the menu (e.g. for a page change)
    while (outcome == MENU_ITEM_REFRESH) {
        ui_clear();

        // print status and board information 
        printf("This Pico has board id %s\n", wifi_settings_get_board_id_hex());
        printf("%s\n%s\n%s\n\n",
                status_summary.settings_file_status,
                status_summary.connect_status,
                status_summary.ip_status);
        fflush(stdout);

        // Calculate the bounds of the current page
        const int page_start_index = current_page_number * MENU_ITEMS_PER_PAGE;
        const int page_end_index = 
            ((page_start_index + MENU_ITEMS_PER_PAGE) < menu->num_items) ? 
                (page_start_index + MENU_ITEMS_PER_PAGE) : menu->num_items;

        // Draw the current page
        cursor_go_to_line(MENU_CAPTION_LINE);
        printf("%s", caption);
        if (num_pages > 1) {
            printf(" (page %d of %d)", current_page_number + 1, num_pages);
        }
        for (int i = page_start_index; i < page_end_index; i++) {
            draw_menu_item(menu, i, current_cursor_index, page_start_index);
        }
        draw_menu_footer(page_start_index, page_end_index, menu->num_items);

        // Wait for the user to decide what to do
        outcome = MENU_ITEM_NOTHING;
        while (outcome == MENU_ITEM_NOTHING) {
            int code = tolower(ui_getchar_timeout_us(1000000));
            int chosen_index = -1;

            switch (code) {
                case CONTROL_C:
                case CONTROL_D:
                case 'q':
                case BACKSPACE:
                    // various ways to say 'cancel'
                    // (always works even if there is no explicit cancel option)
                    outcome = MENU_ITEM_CANCEL;
                    break;
                case CONTROL_L:
                    // Refresh forced
                    outcome = MENU_ITEM_REFRESH;
                    break;
                case KEY_UP:
                    // Cursor moves up
                    if ((current_cursor_index < page_start_index)
                    || (current_cursor_index >= page_end_index)) {
                        // Cursor is not anywhere on screen:
                        // go to the bottom of the menu
                        current_cursor_index = page_end_index - 1;
                    } else {
                        // Redraw the line currently containing the cursor (if any)
                        draw_menu_item(menu, current_cursor_index, -1, page_start_index);
                        // Move up
                        current_cursor_index--;
                        if (current_cursor_index < 0) {
                            // prevent cursor moving beyond the beginning of the menu
                            current_cursor_index = 0;
                        } else if (current_cursor_index < page_start_index) {
                            // previous page
                            outcome = MENU_ITEM_REFRESH;
                            current_page_number--;
                        }
                    }
                    // Redraw the line that now contains the cursor (if it is visible)
                    draw_menu_item(menu, current_cursor_index,
                            current_cursor_index, page_start_index);
                    break;
                case KEY_DOWN:
                    // Cursor moves down
                    if ((current_cursor_index < page_start_index)
                    || (current_cursor_index >= page_end_index)) {
                        // Cursor is not anywhere on screen:
                        // go to the top of the menu
                        current_cursor_index = page_start_index;
                    } else {
                        // Redraw the line currently containing the cursor (if any)
                        draw_menu_item(menu, current_cursor_index, -1, page_start_index);
                        // Move down
                        current_cursor_index++;
                        if (current_cursor_index >= menu->num_items) {
                            // prevent cursor moving beyond the end of the menu
                            current_cursor_index = menu->num_items - 1;
                        } else if (current_cursor_index >= page_end_index) {
                            // next page
                            outcome = MENU_ITEM_REFRESH;
                            current_page_number++;
                        }
                    }
                    // Redraw the line that now contains the cursor (if it is visible)
                    draw_menu_item(menu, current_cursor_index,
                            current_cursor_index, page_start_index);
                    break;
                case KEY_LEFT:
                case 'p':
                    // Go to previous page
                    if (page_start_index > 0) {
                        outcome = MENU_ITEM_REFRESH;
                        current_page_number--;
                    }
                    break;
                case KEY_RIGHT:
                case 'n':
                    // Go to next page
                    if (page_end_index < menu->num_items) {
                        outcome = MENU_ITEM_REFRESH;
                        current_page_number++;
                    }
                    break;
                case CR:
                case LF:
                    // Enter pressed
                    // If the cursor is visible, select. Otherwise, force refresh)
                    if ((current_cursor_index >= page_start_index)
                    && (current_cursor_index < page_end_index)) {
                        chosen_index = current_cursor_index;
                    } else {
                        outcome = MENU_ITEM_REFRESH;
                    }
                    break;
                default:
                    if (code < 0) {
                        // No key press, check for refresh
                        // the menu will be refreshed whenever the status changes
                        status_summary_t new_status_summary;
                        get_status(&new_status_summary);
                        if (memcmp(&status_summary, &new_status_summary, sizeof(status_summary_t)) != 0) {
                            outcome = MENU_ITEM_REFRESH;
                            memcpy(&status_summary, &new_status_summary, sizeof(status_summary_t));
                        }
                    } else {
                        for (int i = page_start_index; i < page_end_index; i++) {
                            // Check for menu item selection
                            if (get_code_for_item(i, page_start_index) == code) {
                                chosen_index = i;
                                break;
                            }
                        }
                    }
                    break;
            }
            if (chosen_index >= 0) {
                // selection made
                draw_menu_footer(page_start_index, page_end_index, menu->num_items);
                printf(" %c", get_code_for_item(chosen_index, page_start_index));
                // check built-in options
                if (chosen_index == cancel_option_index) {
                    outcome = MENU_ITEM_CANCEL;
                } else if (chosen_index == retry_option_index) {
                    outcome = MENU_ITEM_RETRY;
                } else {
                    outcome = chosen_index;
                }
            }
        }
    }
    cursor_go_to_line(MENU_FOOTER_LINE);
    printf("\n");

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
    int code = ui_getchar_timeout_us(250000);
    if (code == CONTROL_C || code == CONTROL_D) {
        // control-C or control-D: cancel
        return true;
    } else {
        return false;
    }
}

void ui_file_full_error() {
    printf("Error: The wifi-settings file is full. No changes have been made.\n"
           "You need to delete some other keys to make space.\n");
    ui_wait_for_the_user();
}

