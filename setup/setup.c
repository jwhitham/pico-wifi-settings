/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Setup app for pico-wifi-settings.
 *
 * This is a combined demonstration of the usage of wifi-settings library
 * and a setup program to help create a valid wifi-settings file
 * with access details for WiFi hotspots.
 */


#include "activity_root.h"

#include "pico/stdlib.h"

#if PICO_CYW43_ARCH_POLL
#error "Background mode is required"
#endif



int main() {
    stdio_init_all();
    activity_root();
    return 1;
}
