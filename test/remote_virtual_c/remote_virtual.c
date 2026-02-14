
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
static const char* g_tcp_port_file;
static const char* g_udp_port_file;

void panic(const char* fmt, ...) {
    fprintf(stderr, "Panic: %s\n", fmt);
    exit(1);
}

static void notify_port_number(const char* port_file, int port) {
    if (!port_file) {
        return;
    }
    FILE* fd = fopen(port_file, "wt");
    if (!fd) {
        return;
    }
    fprintf(fd, "%d\n", port);
    fclose(fd);
}

void notify_tcp_port_number(int port) {
    notify_port_number(g_tcp_port_file, port);
}

void notify_udp_port_number(int port) {
    notify_port_number(g_udp_port_file, port);
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
    if (argc != 4) {
        fprintf(stderr, "Incorrect parameters; usage <tcp port file name> <udp port file name> <secret>\n");
        return 1;
    }
    const char* program = argv[0];
    g_tcp_port_file = argv[1];
    g_udp_port_file = argv[2];
    g_update_secret = argv[3];
    printf("Test server is '%s'\n", program);
    printf("TCP port file is '%s'\n", g_tcp_port_file);
    printf("UDP port file is '%s'\n", g_udp_port_file);
    printf("Secret is '%s'\n", g_update_secret);
        
    int rc = wifi_settings_remote_init();
    ASSERT(rc == 0);

    // Server will shut down when the executable is deleted
    while(access(program, F_OK) == 0) {
        if (!fake_lwip_loop()) {
            usleep(10000);
        }
    }
    return 0;
}


