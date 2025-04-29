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
#include "pico/multicore.h"
#include "pico/flash.h"

#include <string.h>

#if PICO_CYW43_ARCH_POLL
#error "Background mode is required"
#endif
#ifndef ENABLE_REMOTE_UPDATE
// Flash writing functions from the remote update subsystem are needed
#error "setup app must always be compiled with ENABLE_REMOTE_UPDATE, use -DWIFI_SETTINGS_REMOTE=1 or 2"
#endif

static uint32_t setup_stack[0x8000];

int main() {
    stdio_init_all();
    // Multicore is used in this app because (1) it's enabled by default with Bazel,
    // and (2) this is an example of flash_safe_execute:
    if(!flash_safe_execute_core_init()) {
        panic("unable to put core 0 into safe state");
    }
    // Launch the setup program on core 1 so that we can use a custom stack easily.
    // The Pico SDK allows 4kb of stack per CPU core, which is not enough for this
    // application, as it keeps almost everything on the stack.
    multicore_launch_core1_with_stack(activity_root, setup_stack, sizeof(setup_stack));
    // Core 0 is idle
    while (true) {
        sleep_ms(1000);
    }
}
