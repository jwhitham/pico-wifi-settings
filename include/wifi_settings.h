/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This header file should be #included by your application in order to use pico-wifi-settings features.
 *
 */

#ifndef _WIFI_SETTINGS_H_
#define _WIFI_SETTINGS_H_

#ifdef __cplusplus
extern "C" {
#endif
#include "wifi_settings/wifi_settings_connect.h"
#include "wifi_settings/wifi_settings_flash_storage.h"
#include "wifi_settings/wifi_settings_hostname.h"
#ifdef ENABLE_REMOTE_UPDATE
#include "wifi_settings/wifi_settings_remote.h"
#endif

#ifdef __cplusplus
}
#endif

#endif

