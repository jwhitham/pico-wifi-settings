
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

static const char* g_update_secret;
static const char* g_port_file;

void panic(const char* fmt, ...) {
    fprintf(stderr, "Panic: %s\n", fmt);
    exit(1);
}

void notify_tcp_port_number(int port) {
    if (!g_port_file) {
        return;
    }
    FILE* fd = fopen(g_port_file, "wt");
    if (!fd) {
        return;
    }
    fprintf(fd, "%d\n", port);
    fclose(fd);
}

void notify_udp_port_number(int port) {
}

bool wifi_settings_get_value_for_key(
            const char* key, char* value, uint* value_size) {
    ASSERT(strcmp(key, "update_secret") == 0);

    if (!g_update_secret) {
        return false;
    }
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
    if (argc != 3) {
        fprintf(stderr, "Incorrect parameters; usage <port file name> <secret>\n");
        return 1;
    }
    g_port_file = argv[1];
    g_update_secret = argv[2];
    printf("Port file is '%s'\n", g_port_file);
    printf("Secret is '%s'\n", g_update_secret);
        
    int rc = wifi_settings_remote_init();
    ASSERT(rc == 0);
    while(1) {
        if (!fake_lwip_loop()) {
            usleep(10000);
        }
    }
    return 0;
}


