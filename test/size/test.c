/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test program for determining the size of pico-wifi-settings.
 */


#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "pico/bootrom.h"

#ifdef TEST_MODE_WIFI_SETTINGS
#include "wifi_settings.h"
#endif

#ifdef TEST_MODE_BASIC_WIFI
#include "pico/cyw43_arch.h"
#endif

#ifdef TEST_MODE_SOME_WIFI
#include "lwip/pbuf.h"
#include "lwip/udp.h"
#include "lwip/tcp.h"
#endif

#ifdef TEST_MODE_SHA256
#include "mbedtls/sha256.h"
#include "mbedtls/version.h"
#if MBEDTLS_VERSION_MAJOR < 3
// These names were changed in mbedlts 3.x.x
#define mbedtls_sha256_starts mbedtls_sha256_starts_ret
#define mbedtls_sha256_update mbedtls_sha256_update_ret
#define mbedtls_sha256_finish mbedtls_sha256_finish_ret
#endif
#endif

#ifdef TEST_MODE_AES256
#include "mbedtls/aes.h"
#endif

#if PICO_CYW43_ARCH_POLL
#error "Background mode is required"
#endif

#ifdef TEST_MODE_SOME_WIFI
static err_t server_recv(void* arg, struct tcp_pcb* client_pcb, struct pbuf* p, err_t err) {
    tcp_recved(client_pcb, p->tot_len);
    tcp_close(client_pcb);
    pbuf_free(p);
    return 0;
}
static err_t server_accept(void *, struct tcp_pcb *client_pcb, err_t) {
    tcp_recv(client_pcb, server_recv);
    tcp_write(client_pcb, "1", 1, 0);
    return 0;
}
#endif
int main() {
    stdio_init_all();
#ifdef TEST_MODE_BASIC_WIFI
    // Basic WiFi mode with hardcoded settings
    if (cyw43_arch_init() != 0) {
        panic("failed to initialise\n");
        return 1;
    }
    cyw43_arch_enable_sta_mode();
    if (cyw43_arch_wifi_connect_timeout_ms("WIFI_SSID", "WIFI_PASSWORD",
                CYW43_AUTH_WPA2_AES_PSK, 30000)) {
        panic("failed to connect.\n");
        return 1;
    }
#endif
#ifdef TEST_MODE_WIFI_SETTINGS
    // pico-wifi-settings with settings loaded from Flash
    if (wifi_settings_init() != 0) {
        panic("failed to initialise\n");
        return 1;
    }
    wifi_settings_connect();
#endif
#ifdef TEST_MODE_SHA256
    // Use SHA256 functions
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    uint8_t digest_data[32];
    if ((0 != mbedtls_sha256_starts(&ctx, 0))
    || (0 != mbedtls_sha256_update(&ctx, (const uint8_t*) "x", 1))
    || (0 != mbedtls_sha256_finish(&ctx, digest_data))) {
        panic("sha256 failed");
    }
    mbedtls_sha256_free(&ctx);
#endif
#ifdef TEST_MODE_AES256
    // Use AES functions
    mbedtls_aes_context encrypt;
    mbedtls_aes_context decrypt;
    mbedtls_aes_init(&encrypt);
    mbedtls_aes_init(&decrypt);
    uint8_t raw_key[32];
    memset(raw_key, 0, sizeof(raw_key));
    if (0 != mbedtls_aes_setkey_enc(&encrypt, raw_key, sizeof(raw_key) * 8)) {
        panic("aes failed");
    }
    if (0 != mbedtls_aes_setkey_dec(&decrypt, raw_key, sizeof(raw_key) * 8)) {
        panic("aes failed");
    }
    uint8_t encrypt_iv[16];
    uint8_t src[16];
    uint8_t dest[16];
    memset(encrypt_iv, 0, sizeof(src));
    memset(src, 0, sizeof(src));
    if (0 != mbedtls_aes_crypt_cbc(&encrypt, MBEDTLS_AES_ENCRYPT,
                          sizeof(src), encrypt_iv, src, dest)) {
        panic("encrypt_block failed");
    }
#endif

    const int size = 100;
#ifdef TEST_MODE_SOME_WIFI
    // Use LWIP functions
    // Bind UDP port
    ip_addr_t udp_addr;
    ipaddr_aton("255.255.255.255", &udp_addr);
    struct udp_pcb* udp_pcb = udp_new();
    if (!udp_pcb) {
        panic("udp_new failed");
    }
    // Start TCP service
    struct tcp_pcb* port_pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    if (!port_pcb) {
        panic("tcp_new_ip_type failed");
    }
    tcp_bind(port_pcb, NULL, 1234);
    struct tcp_pcb* srv_pcb = tcp_listen_with_backlog(port_pcb, 1);
    if (!srv_pcb) {
        panic("tcp_listen failed");
    }
    tcp_accept(srv_pcb, server_accept);
#endif

    // Use basic functions that would be used in many programs
    char* x = calloc(1, size);
    if (!x) {
        panic("calloc failed");
    }
    memset(x, '0', size);
    x[size - 1] = '\0';
    if (strstr(x, "00000") == NULL) {
        panic("should find");
    }
    if (strcmp(x, "a") >= 0) {
        panic("should be less");
    }
    if (strtol(x, NULL, 0) != 0) {
        panic("should be zero");
    }

    // Loop for sending data
    for (int i = 0; i < 10; i++) {
        printf("Test %d %p\n", i, x);
        sleep_ms(1000);

#ifdef TEST_MODE_SOME_WIFI
        struct pbuf *p = pbuf_alloc(PBUF_TRANSPORT, size, PBUF_RAM);
        memset(p->payload, 0, size);
        udp_sendto(udp_pcb, p, &udp_addr, 1234);
        pbuf_free(p);
#endif
    }
    free(x);
    printf("Size test program completed!\n");
    fflush(stdout);
    reset_usb_boot(0, 0);
    return 0;
}
