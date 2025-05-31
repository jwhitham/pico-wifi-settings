/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This header file declares functions for the remote update service for
 * pico-wifi-settings.
 *
 * You would normally only need to include "wifi_settings.h" in your application.
 *
 */

#ifndef _WIFI_SETTINGS_REMOTE_H_
#define _WIFI_SETTINGS_REMOTE_H_

#include <stdbool.h>
#include <stdint.h>

#define ID_FIRST_USER_HANDLER   128
#define ID_LAST_USER_HANDLER    143
#define MAX_DATA_SIZE           4096


/// @brief Callback function for a handler.
/// The handler is called when a request is received with a msg_type previously registered with
/// wifi_settings_remote_set_handler.
/// 
/// The user sends a (network) message containing a msg_type, some data (perhaps 0 bytes)
/// and a parameter (int32_t) - all of these are received, decrypted (AES-256),
/// and integrity checked (SHA-256) before the handler is invoked with
/// correct msg_type, data_buffer, input_data_size and input_parameter arguments.
///
/// The function returns an int32_t which is passed back to the caller,
/// and may also return some data. The function must set *output_data_size to
/// the number of bytes being returned.
///
/// @param[in] msg_type Message type (passed to wifi_settings_remote_set_handler)
/// @param[inout] data_buffer Data in the request, and data to send in the reply
/// @param[in] input_data_size Size of input in bytes
/// @param[in] input_parameter Value of parameter in the request
/// @param[inout] output_data_size When called, this is the size of the buffer;
/// the function should set it to the number of bytes actually used.
/// @param[in] arg Opaque user data for the function
/// @return Value to be returned to the caller.
typedef int32_t (* handler_callback1_t) (
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg);

/// @brief Callback function for the second part of a two-part handler.
/// The handler is called after a request is received with a msg_type previously registered with
/// wifi_settings_remote_set_handler, and after an acknowledgment is sent.
/// 
/// This second handler cannot return a value or any data. The purpose of two-part
/// handlers is to support requests that put the Pico offline (e.g. reboot) as these
/// have to be acknowledged before they are executed. Usually the first part will be
/// used for validation, returning a non-zero value if validation fails, and then the second
/// part will check the return value from the first, which is input_parameter, and proceed
/// only if validation was ok.
///
/// @param[in] msg_type Message type (passed to wifi_settings_remote_set_handler)
/// @param[inout] data_buffer Data in the request (same as produced by the first handler)
/// @param[in] callback1_data_size Size of input in bytes (*output_data_size from the first handler)
/// @param[in] callback1_return Value of parameter in the request (return value from the first handler)
/// @param[in] arg Opaque user data for the function
typedef void (* handler_callback2_t) (
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t callback1_data_size,
        int32_t callback1_return,
        void* arg);

/// @brief Initialise wifi_settings_remote service
/// @return 0 on success, or an PICO_ERROR code
int wifi_settings_remote_init();

/// @brief Register a handler for a msg_type
/// A remote user can call the handler by placing a valid request with a matching msg_type.
/// This type of handler returns a value and optional data to the user. An acknowledgment and
/// returned data are sent after the handler runs.
/// @param[in] msg_type Identifies the handler; must be in range ID_FIRST_USER_HANDLER ..
/// ID_LAST_USER_HANDLER inclusive.
/// @param[in] handler_callback Pointer to callback function
/// @param[in] arg Opaque user data for the function
/// @return 0 on success, or an PICO_ERROR code
int wifi_settings_remote_set_handler(
        uint8_t msg_type,
        handler_callback1_t callback,
        void* arg);

/// @brief Register a two-stage handler for a msg_type
/// A remote user can call the handler by placing a valid request with a matching msg_type.
/// This type of handler does not return any data, but does return a value (from the first handler).
/// The second handler is called after this value is sent.
/// @param[in] msg_type Identifies the handler; must be in range ID_FIRST_USER_HANDLER ..
/// ID_LAST_USER_HANDLER inclusive.
/// @param[in] callback1 Pointer to first stage function
/// @param[in] callback2 Pointer to second stage function
/// @param[in] arg Opaque user data for the function
/// @return 0 on success, or an PICO_ERROR code
int wifi_settings_remote_set_two_stage_handler(
        uint8_t msg_type,
        handler_callback1_t callback1,
        handler_callback2_t callback2,
        void* arg);

/// @brief Re-read the wifi_settings file in Flash to obtain update_secret,
/// this should be called if the secret is updated in memory so that the new
/// value is used. (Note, this is called by wifi_settings_remote_init).
void wifi_settings_remote_update_secret();

#endif
