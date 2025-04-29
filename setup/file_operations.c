/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * wifi-settings file operations
 */

#include "file_operations.h"
#include "wifi_settings/wifi_settings_flash_range.h"
#include "wifi_settings/wifi_settings_flash_storage_update.h"

#include <string.h>

typedef struct find_index_result_t {
    int key_index, value_index, end_index;
} find_index_result_t;

static bool is_end_of_file_char(char value) {
    switch ((unsigned char) value) {
        case '\0':
        case '\xff':
        case '\x1b':
            return true;
        default:
            return false;
    }
}

static bool is_end_of_line_char(char value) {
    switch (value) {
        case '\r':
        case '\n':
            return true;
        default:
            return is_end_of_file_char(value);
    }
}

static int get_file_size(const file_handle_t* fh) {
    int index;
    for (index = 0; index < (int) WIFI_SETTINGS_FILE_SIZE; index++) {
        if (is_end_of_file_char(fh->contents[index])) {
            break;
        }
    }
    return index;
}

/// @brief Find the space occupied by the next key=value
/// (starting the search at fir->end_index)
static bool find_next_key(const file_handle_t* fh, find_index_result_t* fir) {
    int index = fir->end_index;

    // While searching for the next key
    while (true) {
        // Find next non-EOL character
        while (is_end_of_line_char(fh->contents[index])) {
            // EOF characters are a subset of EOL characters
            if (is_end_of_file_char(fh->contents[index])) {
                return false; // Reached EOF without finding any key
            }
            index++;
            if (index >= (int) WIFI_SETTINGS_FILE_SIZE) {
                return false; // Reached EOF without finding any key
            }
        }
        // This is the start of a line - search here for '=' or EOL
        fir->key_index = index;
        while ((fh->contents[index] != '=') && (!is_end_of_line_char(fh->contents[index]))) {
            index++;
            if (index >= (int) WIFI_SETTINGS_FILE_SIZE) {
                return false; // Reached EOF without finding any key
            }
        }

        // If '=' was found, and it's not right at the beginning of the line
        if ((fh->contents[index] == '=')
        && (fir->key_index < index)) {
            // Some key=value was found on this line
            index++;
            fir->value_index = index;
            while ((index < (int) WIFI_SETTINGS_FILE_SIZE) && (!is_end_of_line_char(fh->contents[index]))) {
                index++;
            }
            fir->end_index = index;
            // Key found?
            // Note that the key could be 0 length, which is not valid
            return true;
        }
        // If a line begins with '=' there is an empty key, which is not valid.
        // Handle the special case by skipping to the end of the line
        while (!is_end_of_line_char(fh->contents[index])) {
            index++;
            if (index >= (int) WIFI_SETTINGS_FILE_SIZE) {
                return false; // Reached EOF without finding any key
            }
        }
        // If this point is reached, we are at an EOL character and about to move to another line.
    }
}

/// @brief Find the space occupied by key=value
static bool find_index(const file_handle_t* fh, const char* key, find_index_result_t* fir) {
    // Initialise search to the start of the file
    fir->key_index = fir->value_index = fir->end_index = 0;
    const int wanted_key_size = (int) strlen(key);

    // While searching for a specific key
    while (find_next_key(fh, fir)) {
        const int this_key_size = (fir->value_index - fir->key_index) - 1;
        if ((this_key_size == wanted_key_size)
        && (strncmp(key, &fh->contents[fir->key_index], this_key_size) == 0)) {
            // Found the key
            return true;
        }
        // If this point is reached, find_next_key will proceed from fir->end_index
    }
    return false;
}

/// @brief Copy part of the file into a nul-terminated string provided by the caller,
/// limiting the size appropriately
static int copy_bytes_needed(
            const file_handle_t* fh,
            const int start_index, const int bytes_needed,
            char *value, const int value_size) {
    int bytes_used = bytes_needed;
    if (bytes_used > value_size) {
        bytes_used = value_size;
    }
    if (bytes_used > 0) {
        memcpy(value, &fh->contents[start_index], bytes_used - 1);
        value[bytes_used - 1] = '\0';
    }
    return bytes_needed;
}

/// @brief Create a gap in the file (possibly 0 length) for adding or removing keys
static bool create_gap(
            file_handle_t* fh,
            const int replace_index, const int remove_size,
            const int gap_size) {

    const int current_file_size = get_file_size(fh);
    const int new_file_size = current_file_size + gap_size - remove_size;

    if ((replace_index < 0) || (remove_size < 0) || (gap_size < 0)) {
        return false; // error - the parameters don't make sense
    }
    if ((replace_index + remove_size) > current_file_size) {
        return false; // error - the section to be removed goes beyond the end of the file
    }
    if (new_file_size > (int) WIFI_SETTINGS_FILE_SIZE) {
        return false; // error - the section to be inserted goes beyond the end of the file
    }

    if (new_file_size != current_file_size) {
        // The file size will change - move the contents
        const int move_to_index = replace_index + gap_size;
        const int move_from_index = replace_index + remove_size;
        memmove(&fh->contents[move_to_index], &fh->contents[move_from_index], current_file_size - move_from_index);

        // mark new EOF
        memset(&fh->contents[new_file_size], '\xff', WIFI_SETTINGS_FILE_SIZE - new_file_size);
    }

    if (gap_size > 0) {
        // leave a placeholder in the gap
        memset(&fh->contents[replace_index], ' ', gap_size);
    }
    return true;
}

/// @brief Include any line ending characters within end_index
static void include_line_ending(const file_handle_t* fh, find_index_result_t* fir) {
    while ((fir->end_index < (int) WIFI_SETTINGS_FILE_SIZE)
    && !is_end_of_file_char(fh->contents[fir->end_index])
    && is_end_of_line_char(fh->contents[fir->end_index])) {
        fir->end_index++;
    }
}

void file_load(file_handle_t* fh) {
    wifi_settings_flash_range_t fr;
    wifi_settings_logical_range_t lr;

    wifi_settings_range_get_wifi_settings_file(&fr);
    wifi_settings_range_translate_to_logical(&fr, &lr);

    memcpy(fh->contents, lr.start_address, WIFI_SETTINGS_FILE_SIZE);
}

void file_discard(file_handle_t* fh, const char* key) {
    find_index_result_t fir;

    while (find_index(fh, key, &fir)) {
        include_line_ending(fh, &fir);

        const int replace_index = fir.key_index;
        const int remove_size = fir.end_index - fir.key_index;

        if (!create_gap(fh, replace_index, remove_size, 0)) {
            // this should not happen, the file should only become smaller,
            // but other errors might occur, so be defensive and abandon the discard attempt
            break;
        }
    }
}

bool file_set(file_handle_t* fh, const char* key, const char* value) {
    // How much space is needed?
    const int key_size = (int) strlen(key);
    const int value_size = (int) strlen(value);
    const int total_size = (int) value_size + 2 + key_size; // 2 bytes: '=' and '\n'

    // Find first copy of the key if present
    find_index_result_t fir;

    if (find_index(fh, key, &fir)) {
        // Key found. Also remove line ending characters after the key
        include_line_ending(fh, &fir);
    } else {
        // Key does not exist - put it after the final end of line character in the file
        // (The last line in the file might be incomplete, so insert at the beginning
        // of that line, rather than appending to whatever is already there.)
        int place_index = get_file_size(fh);
        while ((place_index > 0) && !is_end_of_line_char(fh->contents[place_index - 1])) {
            place_index--;
        }
        fir.key_index = fir.value_index = fir.end_index = place_index;
    }
    const int replace_index = fir.key_index;
    const int remove_size = fir.end_index - fir.key_index;

    // Create space for the new value
    if (!create_gap(fh, replace_index, remove_size, total_size)) {
        return false; // unable to add, not enough space
    }

    // Insert new key=value
    memcpy(&fh->contents[replace_index], key, key_size);
    fh->contents[replace_index + key_size] = '=';
    memcpy(&fh->contents[replace_index + key_size + 1], value, value_size);
    fh->contents[replace_index + total_size - 1] = '\n';
    return true;
}

bool file_contains(const file_handle_t* fh, const char* key) {
    find_index_result_t fir;
    return find_index(fh, key, &fir);
}

int file_get(const file_handle_t* fh, const char* key, char* value, const int value_size) {
    find_index_result_t fir;

    if (value_size > 0) {
        value[0] = '\0'; // defensive: always output a valid string
    }
    if (!find_index(fh, key, &fir)) {
        return -1;
    }
    return copy_bytes_needed(fh, fir.value_index, 1 + fir.end_index - fir.value_index, value, value_size);
}

int file_get_next_key_value(
            const file_handle_t* fh, int* search_index,
            char *key, const int key_size,
            char *value, const int value_size) {

    if (key_size > 0) {
        key[0] = '\0'; // defensive: always output a valid string
    }
    if (value_size > 0) {
        value[0] = '\0';
    }

    find_index_result_t fir;
    fir.key_index = fir.value_index = 0;
    fir.end_index = *search_index;

    if (!find_next_key(fh, &fir)) {
        // There are no more keys
        *search_index = (int) WIFI_SETTINGS_FILE_SIZE;
        return -1;
    }

    // search would continue after this key=value pair
    *search_index = fir.end_index;
    // copy value
    copy_bytes_needed(fh, fir.value_index, 1 + fir.end_index - fir.value_index, value, value_size);
    // copy key
    return copy_bytes_needed(fh, fir.key_index, fir.value_index - fir.key_index, key, key_size);
}


int file_save(const file_handle_t* fh) {
    return wifi_settings_update_flash_safe(fh->contents, get_file_size(fh));
}
