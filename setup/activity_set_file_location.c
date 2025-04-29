/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Set the wifi-settings file location (and move it around)
 */


#include "activity_set_file_location.h"
#include "user_interface.h"
#include "file_finder.h"
#include "file_operations.h"

#include "wifi_settings/wifi_settings_flash_range.h"
#include "wifi_settings/wifi_settings_configuration.h"

#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

typedef enum {
    DO_NOTHING,
    ALWAYS_FORMAT,
    ALWAYS_MOVE,
    ALWAYS_USE,
    CAN_MOVE,
} choice_t;

void activity_set_file_location() {
    ui_clear();

    // Find the end of the program and the end of Flash
    wifi_settings_flash_range_t program_range;
    wifi_settings_range_get_program(&program_range);
    wifi_settings_range_align_to_sector(&program_range);
    const uint32_t minimum = program_range.start_address + program_range.size;

    wifi_settings_flash_range_t flash_range;
    wifi_settings_range_get_all(&flash_range);
    const uint32_t maximum = flash_range.start_address + flash_range.size - WIFI_SETTINGS_FILE_SIZE;

    // Examine existing location
    wifi_settings_flash_range_t old_file_range;
    wifi_settings_range_get_wifi_settings_file(&old_file_range);
    wifi_settings_logical_range_t lr;
    wifi_settings_range_translate_to_logical(&old_file_range, &lr);

    const uint32_t old_address = old_file_range.start_address;
    const file_status_t old_address_status = file_finder_get_status();
    const uint32_t default_address = WIFI_SETTINGS_FILE_ADDRESS;

    printf("Please enter the location for the wifi-settings file.\n"
           "- The default (and recommended) location is 0x%x.\n",
           (uint) default_address);
    printf("- The location is relative to the start of Flash,\n"
           "  so location 0x%x means absolute address 0x%x.\n",
           (uint) old_address, (uint) ((uintptr_t) lr.start_address));
    printf("- The new location must be a multiple of the file size, 0x%x bytes.\n",
           WIFI_SETTINGS_FILE_SIZE);
    printf("- The minimum possible location is 0x%x - the end of the program;\n"
           "  note that other programs may be much larger than this setup app.\n"
           "- The maximum possible location is 0x%x - the end of Flash, minus\n"
           "  0x%x bytes for the file contents.\n",
           (uint) minimum,
           (uint) maximum,
           WIFI_SETTINGS_FILE_SIZE);
    printf("\nThe current location is 0x%x:\n",
           (uint) old_address);
    switch (old_address_status) {
        case FILE_IS_CORRUPT:
            printf("- 0x%x appears to contain data other than a wifi-settings file;\n"
                   "  this data could be unused, or it might be required by some part\n"
                   "  of your application. If you're not sure, use a different location.\n",
                   (uint) old_address);
            break;
        case FILE_HAS_WIFI_DETAILS:
            printf("- 0x%x contains a valid wifi-settings file\n",
                   (uint) old_address);
            break;
        case FILE_HAS_PLACEHOLDER:
            printf("- 0x%x contains a valid placeholder for a wifi-settings file\n",
                   (uint) old_address);
            break;
        default:
            printf("- 0x%x is an empty location\n",
                   (uint) old_address);
            break;
    }
    printf("\nEnter the location:\n");

    char field[16];
    char *endptr = NULL;
    snprintf(field, sizeof(field), "0x%x", (uint) old_address);

    if ((!ui_text_entry(field, sizeof(field))) || (strlen(field) == 0)) {
        return; // cancel
    }

    const uint32_t new_address = (uint) strtol(field, &endptr, 16);
    if (*endptr != '\0') {
        printf("That location is not a valid hex number (0x...).\n");
        ui_wait_for_the_user();
        return;
    }
    if ((new_address < minimum) || (new_address > maximum)) {
        printf("That location is outside of the allowed range 0x%x .. 0x%x.\n",
                (uint) minimum, (uint) maximum);
        ui_wait_for_the_user();
        return;
    }
    if ((new_address % WIFI_SETTINGS_FILE_SIZE) != 0) {
        printf("That location is not a multiple of the file size, 0x%x.\n",
                WIFI_SETTINGS_FILE_SIZE);
        ui_wait_for_the_user();
        return;
    }
    // If the location is the same, that's a special case
    if (old_address == new_address) {
        switch (old_address_status) {
            case FILE_HAS_WIFI_DETAILS:
            case FILE_HAS_PLACEHOLDER:
                // Address unchanged and file is valid - do nothing
                return;
            default:
                // Address unchanged and file is not valid - so formatting is the way to go.
                break;
        }
    }

    // Examine the new address
    file_finder_set_address(new_address);
    const file_status_t new_address_status = file_finder_get_status();
    file_finder_set_address(old_address);

    // Based on the contents of the old and new address, what can the user do?
    choice_t choice = DO_NOTHING;
    switch (new_address_status) {
        case FILE_IS_CORRUPT:
            printf("0x%x appears to contain data other than a wifi-settings file;\n"
                   "this data could be unused, or it might be required by some part\n"
                   "of your application.\n",
                   (uint) new_address);
            switch (old_address_status) {
                case FILE_HAS_WIFI_DETAILS:
                case FILE_HAS_PLACEHOLDER:
                    choice = ALWAYS_MOVE;
                    break;
                default:
                    choice = ALWAYS_FORMAT;
                    break;
            }
            break;
        case FILE_HAS_WIFI_DETAILS:
            printf("0x%x contains a valid wifi-settings file\n",
                   (uint) new_address);
            switch (old_address_status) {
                case FILE_HAS_WIFI_DETAILS:
                case FILE_HAS_PLACEHOLDER:
                    choice = CAN_MOVE;
                    break;
                default:
                    choice = ALWAYS_USE;
                    break;
            }
            break;
        case FILE_HAS_PLACEHOLDER:
            printf("0x%x contains a valid placeholder for a wifi-settings file\n",
                   (uint) new_address);
            switch (old_address_status) {
                case FILE_HAS_WIFI_DETAILS:
                case FILE_HAS_PLACEHOLDER:
                    choice = CAN_MOVE;
                    break;
                default:
                    choice = ALWAYS_USE;
                    break;
            }
            break;
        default:
            printf("0x%x is an empty location\n",
                   (uint) new_address);
            switch (old_address_status) {
                case FILE_HAS_WIFI_DETAILS:
                case FILE_HAS_PLACEHOLDER:
                    choice = ALWAYS_MOVE;
                    break;
                default:
                    choice = ALWAYS_FORMAT;
                    break;
            }
            break;
    }
    // Ask the user what to do
    switch (choice) {
        case ALWAYS_FORMAT:
            printf("If you proceed, 0x%x will be formatted, making it ready\n"
                   "for storing WiFi settings. Would you like to proceed?\n",
                   (uint) new_address);
            if (!ui_choose_yes_or_no()) {
                choice = DO_NOTHING;
            }
            break;
        case ALWAYS_MOVE:
            printf("If you proceed, 0x%x will be moved to 0x%x\n"
                   "and the old location 0x%x will be erased.\n"
                   "Would you like to proceed?\n",
                   (uint) old_address, (uint) new_address,
                   (uint) old_address);
            if (!ui_choose_yes_or_no()) {
                choice = DO_NOTHING;
            }
            break;
        case ALWAYS_USE:
            break;
        case DO_NOTHING:
            break;
        case CAN_MOVE:
            printf("Both 0x%x and 0x%x have WiFi settings.\n"
                   "Would you like to move WiFi settings from 0x%x to 0x%x?\n",
                   (uint) old_address, (uint) new_address,
                   (uint) old_address, (uint) new_address);
            printf("- If you answer yes: 0x%x will be moved to 0x%x and\n"
                   "  the old location 0x%x will be erased.\n",
                   (uint) old_address, (uint) new_address,
                   (uint) old_address);
            printf("- If you answer no: 0x%x will be used for WiFi settings\n"
                   "  and no memory locations will be erased.\n",
                   (uint) new_address);
            if (ui_choose_yes_or_no()) {
                choice = ALWAYS_MOVE;
            } else {
                choice = ALWAYS_USE;
            }
            break;
    }
    // Do whatever the user chose
    bool ok = true;
    switch (choice) {
        case ALWAYS_FORMAT:
            ok = file_finder_set_address_with_format(new_address);
            break;
        case ALWAYS_MOVE:
            ok = file_finder_set_address_with_move(old_address, new_address);
            break;
        case ALWAYS_USE:
            file_finder_set_address(new_address);
            break;
        case CAN_MOVE:
        case DO_NOTHING:
            ok = false;
            break;
    }
    if (ok) {
        printf("0x%x will now be used for WiFi settings.\n",
               (uint) new_address);
        ui_wait_for_the_user();
    }
}
