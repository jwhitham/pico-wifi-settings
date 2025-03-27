
#include "remote_virtual.h"
#include "pico/stdlib.h"
#include "lwip/tcp.h"

#include "wifi_settings/wifi_settings_remote.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>

uint8_t g_update_secret[MAX_SECRET_SIZE + 1];

void panic(const char* fmt, ...) {
    fprintf(stderr, "Panic: %s\n", fmt);
    exit(1);
}

bool wifi_settings_get_value_for_key(
            const char* key, char* value, uint* value_size) {
    ASSERT(strcmp(key, "update_secret") == 0);

    size_t actual_size = strlen(g_update_secret);
    if (actual_size == 0) {
        return false;
    } else {
        if (actual_size < *value_size) {
            *value_size = actual_size;
        }
        memcpy(value, g_update_secret, *value_size);
        return true;
    }
}

int main(int argc, char ** argv) {
    if (argc <= 1) {
        g_update_secret[0] = '\0';
        printf("Secret is unset\n");
    } else if (argc == 2) {
        strncpy(g_update_secret, argv[1], MAX_SECRET_SIZE);
        g_update_secret[MAX_SECRET_SIZE] = '\0';
        printf("Secret is '%s'\n", g_update_secret);
    } else if (argc > 2) {
        fprintf(stderr, "Incorrect parameters\n");
        return 1;
    }
        
    int rc = wifi_settings_remote_init();
    ASSERT(rc == 0);
    while(1) {
        if (!fake_lwip_loop()) {
            usleep(10000);
        }
    }
    return 0;
}


