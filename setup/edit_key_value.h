/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Editor function for a generic key
 */

#ifndef EDIT_KEY_VALUE_H
#define EDIT_KEY_VALUE_H

#include "file_operations.h"

#include <stdbool.h>

typedef bool (* key_value_accept_callback_t) (const char* key, char* value);

/// @brief Edit a value for a generic key
/// @param[in] fh File handle where the key=value pair will be stored
/// @param[in] key Key to be edited
/// @param[in] custom_description if not NULL, this is printed before asking the user for the value
/// @param[in] always_discard_when_empty if true, the key is discarded if the user fills in an empty value,
/// whereas if false, the user is asked what to do in this case
/// @param[in] accept_callback if not NULL, this is called after the user enters a value, if it
/// returns true, the new value is acceptable. The callback can modify the value if desired.
/// @return false if the operation was cancelled, true otherwise (note that true does not mean
/// that the key=value pair is present, it may have been deleted or left unchanged)
bool edit_key_value(
            file_handle_t* fh,
            const char* key,
            const char* custom_description,
            bool always_discard_when_empty,
            key_value_accept_callback_t accept_callback);

#endif
