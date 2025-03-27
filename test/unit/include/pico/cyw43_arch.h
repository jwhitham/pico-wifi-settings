#ifndef PICO_CYW43_ARCH_H
#define PICO_CYW43_ARCH_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#include "pico/async_context.h"

#include <stddef.h>
#include <stdint.h>

typedef struct cyw43_t {
    int nothing;
} cyw43_t;
typedef struct netif {
    int nothing;
} netif;
typedef struct ip4_addr_t{
    uint32_t addr;
} ip4_addr_t;
typedef struct cyw43_ev_scan_result_t{
    uint8_t bssid[6];
    uint8_t ssid[32];
    uint8_t ssid_len;
} cyw43_ev_scan_result_t;
typedef struct cyw43_wifi_scan_options_t {
    int nothing;
} cyw43_wifi_scan_options_t;

extern cyw43_t cyw43_state;
extern netif* netif_default;

#define CYW43_ITF_STA 1000          // unit testing value only
#define CYW43_LINK_DOWN 1001        // unit testing value only
#define CYW43_LINK_JOIN 1002        // unit testing value only
#define CYW43_LINK_NOIP 1003        // unit testing value only
#define CYW43_LINK_UP 1004          // unit testing value only
#define CYW43_LINK_FAIL 1005        // unit testing value only
#define CYW43_LINK_NONET 1006       // unit testing value only
#define CYW43_LINK_BADAUTH 1007     // unit testing value only
#define CYW43_AUTH_WPA2_AES_PSK 1008// unit testing value only
#define CYW43_AUTH_OPEN 1009        // unit testing value only
#define CYW43_CHANNEL_NONE 1010     // unit testing value only
#define PICO_CYW43_ARCH_DEFAULT_COUNTRY_CODE 1011
#define MY_IP_ADDRESS 1012
#define MY_NETMASK 1013
#define MY_GATEWAY 1014
#define CYW43_COUNTRY(A, B, REV) ((unsigned char)(A) | ((unsigned char)(B) << 8) | ((REV) << 16))

void cyw43_arch_lwip_begin();
void cyw43_arch_lwip_end();
int cyw43_wifi_link_status(cyw43_t *self, int itf);
int cyw43_wifi_get_rssi(cyw43_t *self, int32_t *rssi);
int cyw43_wifi_leave(cyw43_t *self, int itf);
bool cyw43_wifi_scan_active(cyw43_t *self);
int cyw43_wifi_join(cyw43_t *self, size_t ssid_len,
        const uint8_t *ssid, size_t key_len,
        const uint8_t *key, uint32_t auth_type,
        const uint8_t *bssid, uint32_t channel);
int cyw43_wifi_scan(cyw43_t *self, cyw43_wifi_scan_options_t *opts,
        void *env,
        int (*result_cb)(void *, const cyw43_ev_scan_result_t *));
int cyw43_arch_init_with_country(uint32_t country);
void cyw43_arch_enable_sta_mode(void);
void cyw43_arch_deinit(void);
async_context_t *cyw43_arch_async_context(void);
bool netif_is_link_up(struct netif *netif);
void netif_set_hostname(struct netif *netif, const char *hostname);
char *ip4addr_ntoa_r(const ip4_addr_t *addr, char *buf, int buflen);
const ip4_addr_t* netif_ip4_addr(struct netif *netif);
const ip4_addr_t* netif_ip4_netmask(struct netif *netif);
const ip4_addr_t* netif_ip4_gw(struct netif *netif);

#endif
