/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * User interface functions
 */

#ifndef USER_INTERFACE_H
#define USER_INTERFACE_H

#include "pico/stdlib.h"

#define MAX_DESCRIPTION_SIZE            75
#define MAX_EDIT_LINE_LENGTH            73
#define MAX_MENU_ITEMS                  240
#define CONTROL_RIGHT_SQUARE_BRACKET    0x1d // control+] (exit from telnet)

typedef struct menu_item_t {
    char description[MAX_DESCRIPTION_SIZE];
    void* arg;
} menu_item_t;

typedef struct menu_t {
    menu_item_t item[MAX_MENU_ITEMS];
    int num_items;
    int max_items;
    uint flags;
} menu_t;

struct file_handle_t;

#define MENU_ITEM_REFRESH               -1
#define MENU_ITEM_CANCEL                -2
#define MENU_ITEM_RETRY                 -3
#define MENU_ITEM_NOTHING               -4
#define MENU_ITEM_NO_MORE_SPACE         -5
#define MENU_FLAG_ENABLE_CANCEL         (1 << 0)
#define MENU_FLAG_ENABLE_RETRY          (1 << 1)

void ui_clear();
void ui_wait_for_the_user();
bool ui_choose_yes_or_no();
bool ui_text_entry(char* buffer, uint max_buffer_size);

void ui_menu_init(menu_t* menu, uint flags);
int ui_menu_add_item(menu_t* menu, void* arg, const char* format, ...);
int ui_menu_show(menu_t* menu, const char* caption);
void* ui_menu_get_arg(menu_t* menu, int index);

bool ui_ask_for_password(const char* ssid, char* password);
bool ui_file_save(struct file_handle_t*);
bool ui_waiting_check_abort();
void ui_file_full_error();

int ui_getchar_timeout_us(uint32_t timeout_us);
int ui_getchar();

#endif
