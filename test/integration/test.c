/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test program for pico-wifi-settings integration.
 *
 * This test program doesn't have any WiFi or IP support
 * until it's added by the integration test.
 */


#include <stdio.h>

#include "pico/stdlib.h"


int main() {
    stdio_init_all();
    for (int i = 0; i < 10; i++) {
        printf("Test %d\n", i);
        sleep_ms(1000);
    }
    return 0;
}
