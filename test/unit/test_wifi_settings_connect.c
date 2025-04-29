/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test for wifi_settings_connect.c
 *
 */

#include "unit_test.h"
#include "wifi_settings/wifi_settings_connect.h"
#define WIFI_SETTINGS_CONNECT_C
#include "wifi_settings/wifi_settings_connect_internal.h"

#include "pico/time.h"
#include "pico/async_context.h"
#include "pico/cyw43_arch.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>


enum mock_state_t {
    MS_START,               // start up (uninitalised)
    MS_PARTIAL_INIT_1,      // called cyw43_arch_init
    MS_PARTIAL_INIT_2,      // called cyw43_arch_enable_sta_mode
    MS_DOWN,                // called async_context_add_at_time_worker
    MS_SCANNING,
    MS_JOIN,
    MS_UP,
    MS_INIT_FAILS,
} mock_state = MS_START;

typedef struct key_value_item_t {
    char key[32];
    uint8_t value_size;
    char value[95];
} key_value_item_t;

#define TEXT_BUFFER_FILL_BYTE 0x1f

static absolute_time_t current_time = {0};
static async_at_time_worker_t *current_worker = NULL;
static int current_link_status = CYW43_LINK_DOWN;
static async_context_t async_context;
static int (*scan_callback)(void *, const cyw43_ev_scan_result_t *);
static ip4_addr_t current_ip_address;
static ip4_addr_t current_netmask;
static ip4_addr_t current_gateway;
static uint32_t country_code;
static uint32_t calls_to_is_link_up;
static uint32_t calls_to_cyw43_wifi_leave;
static uint32_t calls_to_cyw43_wifi_scan_active;
static uint32_t calls_to_netif_ip4_addr;
static key_value_item_t key_value_items[MAX_NUM_SSIDS * 2];
static bool cyw43_arch_lwip_lock = false;
static char connected_ssid[WIFI_SSID_SIZE];
static char connected_bssid[WIFI_BSSID_SIZE];
static char connected_password[WIFI_PASSWORD_SIZE];
static char text_buffer[1000];

cyw43_t cyw43_state;
netif* netif_default;
netif g_netif_default;
extern struct wifi_state_t g_wifi_state;

// Mock implementation of make_timeout_time_ms
absolute_time_t make_timeout_time_ms(const uint32_t ms) {
    return delayed_by_ms(current_time, ms);
}
    
// Mock implementation of delayed_by_ms
absolute_time_t delayed_by_ms(const absolute_time_t t, const uint32_t ms) {
    absolute_time_t t2;
    t2.value = t.value + ms;
    return t2;
}

// Mock implementation of time_reached
bool time_reached(const absolute_time_t t) {
    return t.value <= current_time.value;
}

// Mock implementation of async_context_add_at_time_worker
bool async_context_add_at_time_worker(async_context_t *context,
        async_at_time_worker_t *worker) {
    if (mock_state == MS_PARTIAL_INIT_2) {
        // Being called from wifi_settings_init
        mock_state = MS_DOWN;
        ASSERT(context == &async_context);
        ASSERT(!current_worker);
        current_worker = worker;
    } else {
        // Being called from periodic task
        ASSERT((mock_state == MS_DOWN)
                || (mock_state == MS_SCANNING)
                || (mock_state == MS_JOIN)
                || (mock_state == MS_UP));
        ASSERT(context == &async_context);
        ASSERT(current_worker);
        ASSERT(current_worker == worker);
    }
    return true;
}

// Mock implementation of async_context_remove_at_time_worker
bool async_context_remove_at_time_worker(async_context_t *context,
        async_at_time_worker_t *worker) {
    ASSERT(context == &async_context);
    ASSERT(current_worker);
    ASSERT(current_worker == worker);
    current_worker = NULL;
    return true;
}

// Mock implementation of cyw43_arch_lwip_begin
void cyw43_arch_lwip_begin() {
    ASSERT(!cyw43_arch_lwip_lock);
    ASSERT(mock_state != MS_START);
    cyw43_arch_lwip_lock = true;
}

// Mock implementation of cyw43_arch_lwip_begin
void cyw43_arch_lwip_end() {
    ASSERT(cyw43_arch_lwip_lock);
    ASSERT(mock_state != MS_START);
    cyw43_arch_lwip_lock = false;
}

// Mock implementation of cyw43_wifi_link_status
int cyw43_wifi_link_status(cyw43_t *self, int itf) {
    ASSERT(self == &cyw43_state);
    ASSERT(itf == CYW43_ITF_STA);
    return current_link_status;
}

// Mock implementation of cyw43_wifi_get_rssi
int cyw43_wifi_get_rssi(cyw43_t *self, int32_t *rssi) {
    ASSERT(self == &cyw43_state);
    *rssi = -1;
    return 0;
}

// Mock implementation of cyw43_wifi_scan_active
bool cyw43_wifi_scan_active(cyw43_t *self) {
    ASSERT(self == &cyw43_state);
    calls_to_cyw43_wifi_scan_active++;
    return mock_state == MS_SCANNING;
}

// Mock implementation of cyw43_wifi_join
int cyw43_wifi_join(cyw43_t *self, size_t ssid_len, const uint8_t *ssid,
        size_t key_len, const uint8_t *key, uint32_t auth_type,
        const uint8_t *bssid, uint32_t channel) {
    ASSERT(self == &cyw43_state);
    if (ssid) {
        ASSERT(!bssid);
        ASSERT(ssid_len < WIFI_SSID_SIZE);
        memset(connected_bssid, 0, WIFI_BSSID_SIZE);
        memcpy(connected_ssid, ssid, ssid_len);
        connected_ssid[ssid_len] = '\0';
    } else {
        ASSERT(bssid);
        ASSERT(ssid_len == 0);
        memset(connected_ssid, 0, WIFI_SSID_SIZE);
        memcpy(connected_bssid, bssid, WIFI_BSSID_SIZE);
    }
    ASSERT(key_len < WIFI_PASSWORD_SIZE);
    ASSERT(key);
    ASSERT((auth_type == CYW43_AUTH_WPA2_AES_PSK) || (auth_type == CYW43_AUTH_OPEN));
    if (key_len == 0) {
        ASSERT(auth_type == CYW43_AUTH_OPEN);
    } else {
        ASSERT(auth_type == CYW43_AUTH_WPA2_AES_PSK);
    }
    ASSERT(channel == CYW43_CHANNEL_NONE);
    ASSERT(mock_state == MS_DOWN);
    memcpy(connected_password, key, key_len);
    connected_password[key_len] = '\0';
    mock_state = MS_JOIN;
    return 0;
}

// Mock implementation of cyw43_wifi_leave
int cyw43_wifi_leave(cyw43_t *self, int itf) {
    ASSERT(self == &cyw43_state);
    ASSERT(itf == CYW43_ITF_STA);
    ASSERT((mock_state == MS_JOIN)
            || (mock_state == MS_UP)
            || (mock_state == MS_DOWN));
    calls_to_cyw43_wifi_leave++;
    mock_state = MS_DOWN;
    return 0;
}

// Mock implementation of cyw43_wifi_scan
int cyw43_wifi_scan(cyw43_t *self, cyw43_wifi_scan_options_t *opts,
        void *env,
        int (*result_cb)(void *, const cyw43_ev_scan_result_t *)) {

    ASSERT(self == &cyw43_state);
    ASSERT(opts);
    ASSERT(!env);
    ASSERT(mock_state == MS_DOWN);
    ASSERT(!scan_callback);
    mock_state = MS_SCANNING;
    scan_callback = result_cb;
    return 0;
}

// Mock implementation of cyw43_arch_init_with_country
int cyw43_arch_init_with_country(uint32_t country) {
    if (mock_state == MS_INIT_FAILS) {
        return -1;
    }
    ASSERT(mock_state == MS_START);
    country_code = country;
    mock_state = MS_PARTIAL_INIT_1;
    return 0;
}

// Mock implementation of cyw43_arch_enable_sta_mode
void cyw43_arch_enable_sta_mode(void) {
    ASSERT(mock_state == MS_PARTIAL_INIT_1);
    mock_state = MS_PARTIAL_INIT_2;
    netif_default = &g_netif_default;
}

// Mock implementation of cyw43_arch_deinit
void cyw43_arch_deinit(void) {
    ASSERT(mock_state == MS_DOWN);
    mock_state = MS_START;
}

// Mock implementation of cyw43_arch_async_context
async_context_t *cyw43_arch_async_context(void) {
    ASSERT(mock_state == MS_PARTIAL_INIT_2);
    return &async_context;
}

// Mock implementation of netif_is_link_up
bool netif_is_link_up(struct netif *netif) {
    ASSERT(netif);
    ASSERT(netif == &g_netif_default);
    calls_to_is_link_up++;
    return mock_state == MS_UP;
}

// Mock implementation of netif_set_hostname
void netif_set_hostname(struct netif *netif, const char *) {
    ASSERT(netif);
    ASSERT(netif == &g_netif_default);
}

// Mock implementation of ip4addr_ntoa_r
char *ip4addr_ntoa_r(const ip4_addr_t *addr, char *buf, int buflen) {
    snprintf(buf, buflen, "0.0.0.%u", addr->addr);
    return buf;
}

// Mock implementation of netif_ip4_addr
const ip4_addr_t* netif_ip4_addr(struct netif *netif) {
    ASSERT(netif);
    ASSERT(netif == &g_netif_default);
    calls_to_netif_ip4_addr++;
    return &current_ip_address;
}

// Mock implementation of netif_ip4_netmask
const ip4_addr_t* netif_ip4_netmask(struct netif *netif) {
    ASSERT(netif);
    ASSERT(netif == &g_netif_default);
    return &current_netmask;
}

// Mock implementation of netif_ip4_gw
const ip4_addr_t* netif_ip4_gw(struct netif *netif) {
    ASSERT(netif);
    ASSERT(netif == &g_netif_default);
    return &current_gateway;
}

// Mock implementation of wifi_settings_get_value_for_key
bool wifi_settings_get_value_for_key(
            const char* key, char* value, uint* value_size) {
    for (uint i = 0; i < NUM_ELEMENTS(key_value_items); i++) {
        key_value_item_t* item = &key_value_items[i];
        if (strcmp(item->key, key) == 0) {
            if (*value_size > item->value_size) {
                *value_size = item->value_size;
            }
            memcpy(value, item->value, *value_size);
            return true;
        }
    }
    return false;
}

// Mock implementation of wifi_settings_set_hostname
void wifi_settings_set_hostname() {}

// Mock implementation of wifi_settings_get_hostname
const char* wifi_settings_get_hostname() {
    return "FakeHostname";
}

void set_value_for_key(const char* key, const char* value) {
    uint value_size = strlen(value);
    ASSERT(value_size <= sizeof(key_value_items[0].value));
    ASSERT(strlen(key) < sizeof(key_value_items[0].key));

    // Replace existing value if found
    for (uint i = 0; i < NUM_ELEMENTS(key_value_items); i++) {
        key_value_item_t* item = &key_value_items[i];
        if (strcmp(item->key, key) == 0) {
            memcpy(item->value, value, value_size);
            item->value_size = value_size;
            return;
        }
    }
    // Otherwise, find empty slot
    for (uint i = 0; i < NUM_ELEMENTS(key_value_items); i++) {
        key_value_item_t* item = &key_value_items[i];
        if (item->key[0] == '\0') {
            strcpy(item->key, key);
            memcpy(item->value, value, value_size);
            item->value_size = value_size;
            return;
        }
    }
    ASSERT(false); // no slots found
}

// Reset calls_to... variables
void reset_calls_to() {
    calls_to_cyw43_wifi_leave = 0;
    calls_to_cyw43_wifi_scan_active = 0;
    calls_to_is_link_up = 0;
    calls_to_netif_ip4_addr = 0;
}

// Reset everything
void reset_all() {
    current_time.value = 0;
    current_worker = NULL;
    current_link_status = CYW43_LINK_DOWN;
    scan_callback = NULL;
    current_ip_address.addr = 0;
    current_netmask.addr = 0;
    current_gateway.addr = 0;
    memset(&cyw43_state, 0, sizeof(cyw43_state));
    netif_default = NULL;
    memset(&g_wifi_state, 0, sizeof(g_wifi_state));
    memset(key_value_items, 0, sizeof(key_value_items));
    memset(&g_netif_default, 0, sizeof(g_netif_default));
    country_code = 0;
    reset_calls_to();
    memset(connected_ssid, 0, sizeof(connected_ssid));
    memset(connected_bssid, 0, sizeof(connected_bssid));
    memset(connected_password, 0, sizeof(connected_password));
    memset(text_buffer, TEXT_BUFFER_FILL_BYTE, sizeof(text_buffer));
    text_buffer[sizeof(text_buffer) - 1] = '\0';
    mock_state = MS_START;
    cyw43_arch_lwip_lock = false;
}


void test_wifi_settings_init() {
    // GIVEN uninitialised state
    reset_all();
    // WHEN cyw43_arch_init_with_country fails during wifi_settings_init()
    mock_state = MS_INIT_FAILS;
    int ret = wifi_settings_init();
    // THEN return is non-zero and state is INITIALISATION_ERROR, no setup is performed
    ASSERT(ret != 0);
    ASSERT(g_wifi_state.cstate == INITIALISATION_ERROR);
    ASSERT(!g_wifi_state.periodic_worker.next_time.value);
    ASSERT(!g_wifi_state.context);

    // GIVEN invalid state for initialisation
    reset_all();
    g_wifi_state.cstate = DISCONNECTED;
    // WHEN wifi_settings_init() is called
    ret = wifi_settings_init();
    // THEN return is non-zero
    ASSERT(ret != 0);

    // GIVEN default country code
    reset_all();
    // WHEN wifi_settings_init() is called
    ret = wifi_settings_init();
    // THEN setup tasks are completed as expected
    ASSERT(ret == 0);
    ASSERT(mock_state == MS_DOWN); // init functions were called in the right order
    ASSERT(country_code == PICO_CYW43_ARCH_DEFAULT_COUNTRY_CODE);
    ASSERT(g_wifi_state.connect_timeout_time.value == CONNECT_TIMEOUT_TIME_MS);
    ASSERT(g_wifi_state.scan_holdoff_time.value == INITIAL_SETUP_TIME_MS);
    ASSERT(g_wifi_state.cstate == DISCONNECTED);
    ASSERT(g_wifi_state.context == &async_context);
    ASSERT(g_wifi_state.periodic_worker.next_time.value == INITIAL_SETUP_TIME_MS);
    ASSERT(g_wifi_state.periodic_worker.do_work);

    // GIVEN invalid country code
    reset_all();
    set_value_for_key("country", "x");
    // WHEN wifi_settings_init() is called
    ret = wifi_settings_init();
    // THEN setup tasks are completed as expected with the default country code
    ASSERT(ret == 0);
    ASSERT(country_code == PICO_CYW43_ARCH_DEFAULT_COUNTRY_CODE);

    // GIVEN valid country code
    reset_all();
    set_value_for_key("country", "AX");
    // WHEN wifi_settings_init() is called
    ret = wifi_settings_init();
    // THEN setup tasks are completed as expected with the specified country code
    ASSERT(ret == 0);
    ASSERT(country_code == 0x5841); // "AX"
}

void test_wifi_settings_deinit() {
    // GIVEN some active state
    reset_all();
    int ret = wifi_settings_init();
    ASSERT(ret == 0);
    // WHEN wifi_settings_deinit() is called
    wifi_settings_deinit();
    // THEN state returns to uninitialised
    ASSERT(!g_wifi_state.netif);
    ASSERT(!current_worker); // async_context_remove_at_time_worker() called
    ASSERT(!g_wifi_state.context);
    ASSERT(mock_state == MS_START); // cyw43_wifi_leave(), cyw43_arch_deinit() called
    ASSERT(calls_to_cyw43_wifi_leave == 1);
    ASSERT(g_wifi_state.cstate == UNINITIALISED);
    ASSERT(g_wifi_state.selected_ssid_index == 0);

    // GIVEN some inactive state
    reset_all();
    mock_state = MS_DOWN;
    // WHEN wifi_settings_deinit() is called
    wifi_settings_deinit();
    // THEN state is still uninitialised but cyw43_arch_deinit() was not called
    ASSERT(g_wifi_state.cstate == UNINITIALISED);
    ASSERT(mock_state == MS_DOWN); // cyw43_wifi_leave(), cyw43_arch_deinit() not called
    ASSERT(calls_to_cyw43_wifi_leave == 0);
}

void test_wifi_settings_connect() {
    // GIVEN disconnected state
    reset_all();
    wifi_settings_init();
    ASSERT(g_wifi_state.cstate == DISCONNECTED);
    // WHEN wifi_settings_connect() is called
    wifi_settings_connect();
    // THEN state changes to TRY_TO_CONNECT
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);

    // GIVEN connected state
    reset_all();
    wifi_settings_init();
    g_wifi_state.cstate = CONNECTED_IP;
    // WHEN wifi_settings_connect() is called
    wifi_settings_connect();
    // THEN no state change
    ASSERT(g_wifi_state.cstate == CONNECTED_IP);

    // GIVEN error state
    reset_all();
    wifi_settings_init();
    g_wifi_state.cstate = INITIALISATION_ERROR;
    // WHEN wifi_settings_connect() is called
    wifi_settings_connect();
    // THEN no state change
    ASSERT(g_wifi_state.cstate == INITIALISATION_ERROR);
}

void test_wifi_settings_disconnect() {
    // GIVEN connected state
    reset_all();
    wifi_settings_init();
    g_wifi_state.cstate = CONNECTED_IP;
    g_wifi_state.selected_ssid_index = 1;
    g_wifi_state.netif = &g_netif_default;
    mock_state = MS_UP;
    // WHEN wifi_settings_disconnect() is called
    wifi_settings_disconnect();
    // THEN state change to disconnected (resetting stuff as appropriate)
    ASSERT(mock_state == MS_DOWN);
    ASSERT(calls_to_cyw43_wifi_leave == 1); // cyw43_wifi_leave called
    ASSERT(!g_wifi_state.netif);
    ASSERT(g_wifi_state.cstate == DISCONNECTED);
    ASSERT(!g_wifi_state.selected_ssid_index);

    // GIVEN disconnected state
    reset_all();
    wifi_settings_init();
    mock_state = MS_UP;
    // WHEN wifi_settings_disconnect() is called
    wifi_settings_disconnect();
    // THEN no state change but reset happpens anyway
    ASSERT(mock_state == MS_DOWN); 
    ASSERT(calls_to_cyw43_wifi_leave == 1); // cyw43_wifi_leave called
    ASSERT(!g_wifi_state.netif);
    ASSERT(g_wifi_state.cstate == DISCONNECTED);
    ASSERT(!g_wifi_state.selected_ssid_index);

    // GIVEN uninitialised state
    reset_all();
    mock_state = MS_UP;
    // WHEN wifi_settings_disconnect() is called
    wifi_settings_disconnect();
    // THEN no state change
    ASSERT(mock_state == MS_UP);
    ASSERT(calls_to_cyw43_wifi_leave == 0);
    ASSERT(g_wifi_state.cstate == UNINITIALISED);
}


void test_wifi_settings_is_connected() {
    // GIVEN connected state
    reset_all();
    wifi_settings_init();
    g_wifi_state.cstate = CONNECTED_IP;
    g_wifi_state.selected_ssid_index = 1;
    g_wifi_state.netif = &g_netif_default;
    mock_state = MS_UP;
    // WHEN wifi_settings_is_connected() is called
    bool ret = wifi_settings_is_connected();
    // THEN return true after calling netif_is_link_up (which returns true)
    ASSERT(ret);
    ASSERT(calls_to_is_link_up == 1);

    // GIVEN connected state, but netif is down
    reset_all();
    wifi_settings_init();
    g_wifi_state.cstate = CONNECTED_IP;
    g_wifi_state.selected_ssid_index = 1;
    g_wifi_state.netif = &g_netif_default;
    mock_state = MS_DOWN;
    // WHEN wifi_settings_is_connected() is called
    ret = wifi_settings_is_connected();
    // THEN return false after calling netif_is_link_up (which returns false)
    ASSERT(!ret);
    ASSERT(calls_to_is_link_up == 1);

    // GIVEN disconnected state
    reset_all();
    wifi_settings_init();
    // WHEN wifi_settings_is_connected() is called
    ret = wifi_settings_is_connected();
    // THEN return false without calling netif_is_link_up
    ASSERT(!ret);
    ASSERT(calls_to_is_link_up == 0);
}

void reset_for_state_machine_test() {
    reset_all();
    wifi_settings_init();
    wifi_settings_connect();
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);
    ASSERT(mock_state == MS_DOWN);
    ASSERT(current_worker);
}

void create_ssids(uint count) {
    for (uint i = 1; i <= count; i++) {
        char key[20];
        char value[20];

        snprintf(key, sizeof(key), "ssid%u", i);
        snprintf(value, sizeof(value), "SSID_%u", i);
        set_value_for_key(key, value);
        snprintf(key, sizeof(key), "pass%u", i);
        snprintf(value, sizeof(value), "PASSWORD_%u", i);
        set_value_for_key(key, value);
    }
}

void step_state_machine() {
    ASSERT(current_worker);
    ASSERT(current_worker->do_work);
    if (current_worker->next_time.value > current_time.value) {
        current_time.value = current_worker->next_time.value;
    }
    uint32_t previous_next_time = current_worker->next_time.value;
    current_worker->do_work(&async_context, current_worker);
    ASSERT(current_worker->next_time.value > previous_next_time); // Check that time advanced
}

void test_wifi_storage_empty_state() {
    // GIVEN the TRY_TO_CONNECT state without any wifi hotspots
    reset_for_state_machine_test();

    // WHEN stepping through the state machine
    step_state_machine();

    // THEN forces disconnect and then enters STORAGE_EMPTY_ERROR state
    ASSERT(calls_to_cyw43_wifi_leave == 1);
    ASSERT(calls_to_cyw43_wifi_scan_active == 0);
    ASSERT(g_wifi_state.cstate == STORAGE_EMPTY_ERROR);

    // GIVEN the STORAGE_EMPTY_ERROR state without any wifi hotspots
    // WHEN stepping through the state machine
    step_state_machine();

    // THEN stay in STORAGE_EMPTY_ERROR state
    ASSERT(g_wifi_state.cstate == STORAGE_EMPTY_ERROR);

    // GIVEN the STORAGE_EMPTY_ERROR state with a wifi hotspot
    create_ssids(1);

    // WHEN stepping through the state machine
    step_state_machine();

    // THEN go to TRY_TO_CONNECT state
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);

    // GIVEN the TRY_TO_CONNECT state with some wifi hotspots
    // WHEN stepping through the state machine
    step_state_machine();

    // THEN forces disconnect and then begins a scan
    ASSERT(calls_to_cyw43_wifi_scan_active == 1);
    ASSERT(calls_to_cyw43_wifi_leave == 2);
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);

    // GIVEN the SCANNING state
    mock_state = MS_SCANNING;
    // WHEN stepping
    // THEN stays in SCANNING state forever (waiting for the hardware to finish the scan)
    for (uint i = 0; i < 60; i++) {
        calls_to_cyw43_wifi_scan_active = 0;
        step_state_machine();
        ASSERT(g_wifi_state.cstate == SCANNING);
        ASSERT(calls_to_cyw43_wifi_scan_active == 1);
    }
}

void reach_connecting_state() {
    // GIVEN the TRY_TO_CONNECT state with wifi hotspots
    reset_for_state_machine_test();
    create_ssids(MAX_NUM_SSIDS);

    // WHEN stepping through the state machine
    step_state_machine();

    // THEN forces disconnect and begins a scan
    ASSERT(calls_to_cyw43_wifi_leave == 1);
    ASSERT(calls_to_cyw43_wifi_scan_active == 1);
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);

    // GIVEN the SCANNING state, with nothing found
    ASSERT(g_wifi_state.ssid_scan_info[5] == NOT_FOUND);
    ASSERT(strcmp(wifi_settings_get_ssid_status(5), "NOT FOUND") == 0);
    // WHEN a known SSID is found
    cyw43_ev_scan_result_t scan_result;
    memset(&scan_result, 0, sizeof(scan_result));
    strcpy((char*)scan_result.ssid, "SSID_5");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    // THEN SSID marked as found
    ASSERT(g_wifi_state.ssid_scan_info[5] == FOUND);
    ASSERT(strcmp(wifi_settings_get_ssid_status(5), "FOUND") == 0);

    // GIVEN the SCANNING state
    ASSERT(g_wifi_state.ssid_scan_info[3] == NOT_FOUND);
    // WHEN a known SSID is found
    strcpy((char*)scan_result.ssid, "SSID_3");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    // THEN SSID marked as found
    ASSERT(g_wifi_state.ssid_scan_info[3] == FOUND);

    // GIVEN the SCANNING state
    // WHEN an unknown SSID is found
    memset(&scan_result, 0, sizeof(scan_result));
    strcpy((char*)scan_result.ssid, "Hello");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    // THEN no change in the SSID set - only 3 and 5 were found
    for (uint i = 0; i <= MAX_NUM_SSIDS; i++) {
        if ((i == 3) || (i == 5)) {
            ASSERT(g_wifi_state.ssid_scan_info[i] == FOUND);
        } else {
            ASSERT(g_wifi_state.ssid_scan_info[i] == NOT_FOUND);
        }
    }
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN that scanning ends
    mock_state = MS_DOWN;
    reset_calls_to();
    // WHEN periodic callback runs
    step_state_machine();
    // THEN begin_connecting() is called, state changes to CONNECTING,
    // disconnection is forced, connection begins to SSID_3 (highest priority of those found)
    ASSERT(calls_to_cyw43_wifi_scan_active == 1);   // one final check of whether scan was active
    ASSERT(calls_to_cyw43_wifi_leave == 1);         // disconnection is forced
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(strcmp(connected_ssid, "SSID_3") == 0);  // cyw43_wifi_join called
    ASSERT(connected_bssid[0] == '\0');
    ASSERT(strcmp(connected_password, "PASSWORD_3") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 3);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT); // connection attempt begun
    reset_calls_to();
}

void test_wifi_connecting_state() {
    // GIVEN connecting state, but link status is down, despite calling cyw43_wifi_join, which should change it to CYW43_LINK_JOIN
    reach_connecting_state();
    current_link_status = CYW43_LINK_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == FAILED);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connecting state, but link status is NONET
    reach_connecting_state();
    current_link_status = CYW43_LINK_NONET;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == FAILED);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connecting state, but link status is FAIL
    reach_connecting_state();
    current_link_status = CYW43_LINK_FAIL;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == FAILED);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connecting state, but link status is BADAUTH
    reach_connecting_state();
    current_link_status = CYW43_LINK_BADAUTH;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as BADAUTH
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == BADAUTH);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connecting state, and link status is JOIN
    reach_connecting_state();
    ASSERT(g_wifi_state.cstate == CONNECTING);
    current_link_status = CYW43_LINK_JOIN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (but returns false) and there is no state change
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);

    // GIVEN connecting state, and link status is JOIN, but the timeout is reached
    reach_connecting_state();
    current_link_status = CYW43_LINK_JOIN;
    current_time.value += CONNECT_TIMEOUT_TIME_MS;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as TIMEOUT
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == TIMEOUT);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connecting state, and link status is JOIN, and network link is up
    reach_connecting_state();
    mock_state = MS_UP;
    current_link_status = CYW43_LINK_JOIN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (returns true) and has_valid_address is called (but returns 0.0.0.0)
    // so there is no state change
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(calls_to_netif_ip4_addr == 1);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);
    ASSERT(g_wifi_state.cstate == CONNECTING);
}

void reach_connected_ip_state() {
    // GIVEN connecting state, and link status is JOIN, and network link is up, and there is a valid IP address
    reach_connecting_state();
    mock_state = MS_UP;
    current_ip_address.addr = 1;
    current_link_status = CYW43_LINK_JOIN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (returns true) and netif_ip4_addr is called (returns 0.0.0.1)
    // so the state changes to CONNECTED_IP
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(calls_to_netif_ip4_addr == 1);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == SUCCESS);
    ASSERT(g_wifi_state.cstate == CONNECTED_IP);
    reset_calls_to();
}

void test_wifi_connected_ip_state() {
    // GIVEN connected_ip state, and connection is stable
    reach_connected_ip_state();

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (returns true) and netif_ip4_addr is called (returns 0.0.0.1)
    // and the state doesn't change
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(calls_to_netif_ip4_addr == 1);
    ASSERT(g_wifi_state.cstate == CONNECTED_IP);

    // GIVEN connected_ip state, and connection is not stable, because the IP address is lost
    reach_connected_ip_state();
    current_ip_address.addr = 0;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (returns true) and netif_ip4_addr is called (returns 0.0.0.0)
    // so the IP address is lost and the state changes to TRY_TO_CONNECT
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(calls_to_netif_ip4_addr == 1);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == LOST);
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);

    // GIVEN connected_ip state, and connection is not stable, because the network link goes down
    reach_connected_ip_state();
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN netif_is_link_up is called (returns false)
    // so the IP address is lost and the state changes to TRY_TO_CONNECT
    ASSERT(calls_to_is_link_up == 1);
    ASSERT(calls_to_netif_ip4_addr == 0); // never called as netif_is_link_up is first
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == LOST);
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);
}

void test_wifi_connecting_state_when_lost() {
    // GIVEN connecting state, connection fails
    reach_connecting_state();
    current_link_status = CYW43_LINK_DOWN;
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED
    // The true purpose of entering this state is not to scan for more hotspots
    // but to revisit the existing list of known hotspots and pick another one
    ASSERT(g_wifi_state.selected_ssid_index == 3);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == FAILED);

    // GIVEN scanning state
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(mock_state == MS_DOWN); // not scanning

    // WHEN periodic callback runs
    step_state_machine();

    // THEN after forcing a disconnect, and finding that no scan is active, a new connection begins
    // to the next SSID found by the scan (SSID_5)
    ASSERT(calls_to_cyw43_wifi_leave == 1);
    ASSERT(calls_to_cyw43_wifi_scan_active == 1);
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(g_wifi_state.selected_ssid_index == 5);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);

    // GIVEN connecting state and SSID join in progress
    current_link_status = CYW43_LINK_JOIN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN no state change
    ASSERT(g_wifi_state.selected_ssid_index == 5);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);
    ASSERT(g_wifi_state.cstate == CONNECTING);

    // GIVEN connecting state and SSID join in progress
    current_link_status = CYW43_LINK_JOIN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN no state change
    ASSERT(g_wifi_state.selected_ssid_index == 5);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);
    ASSERT(g_wifi_state.cstate == CONNECTING);

    // GIVEN connecting state and SSID join failed
    current_link_status = CYW43_LINK_DOWN;
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED - again
    ASSERT(g_wifi_state.selected_ssid_index == 5);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == FAILED);

    // GIVEN scanning state
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(mock_state == MS_DOWN); // not scanning - again

    // WHEN periodic callback runs
    step_state_machine();

    // THEN after forcing a disconnect, and finding that no scan is active,
    // begin_connection() is called, but because there are no SSIDs in the FOUND state,
    // the next state is TRY_TO_CONNECT, with no SSID selected
    ASSERT(calls_to_cyw43_wifi_leave == 2);
    ASSERT(calls_to_cyw43_wifi_scan_active == 2);
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);
    ASSERT(g_wifi_state.selected_ssid_index == 0);
    for (uint i = 0; i <= MAX_NUM_SSIDS; i++) {
        if ((i == 3) || (i == 5)) {
            ASSERT(g_wifi_state.ssid_scan_info[i] == FAILED);
        } else {
            ASSERT(g_wifi_state.ssid_scan_info[i] == NOT_FOUND);
        }
    }
}

void test_wifi_connecting_state_when_ssid_details_are_forgotten() {
    // GIVEN scanning state, when about to connect to SSID_5 following a failure
    // to connect to SSID_3, the list of SSIDs previously identified is unexpectedly cleared
    reach_connecting_state();
    current_link_status = CYW43_LINK_DOWN;
    mock_state = MS_DOWN;
    step_state_machine();
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(g_wifi_state.ssid_scan_info[3] == FAILED);   // Just lost connection to this
    ASSERT(strcmp(wifi_settings_get_ssid_status(3), "FAILED") == 0);
    ASSERT(g_wifi_state.ssid_scan_info[5] == FOUND);    // Ready for connection
    ASSERT(strcmp(wifi_settings_get_ssid_status(5), "FOUND") == 0);
    memset(key_value_items, 0, sizeof(key_value_items)); // All SSID details are forgotten!

    // WHEN periodic callback runs
    step_state_machine();

    // THEN the next state is TRY_TO_CONNECT, because the SSID_5 details were lost
    ASSERT(g_wifi_state.cstate == TRY_TO_CONNECT);
    ASSERT(g_wifi_state.ssid_scan_info[5] == ATTEMPT); // Connection attempt was abandoned
    ASSERT(strcmp(wifi_settings_get_ssid_status(5), "ATTEMPT") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 0);
}

void test_wifi_connecting_with_bssid() {
    // GIVEN the scanning state, and hotspot identified by a BSSID
    reset_for_state_machine_test();
    for (uint i = 1; i <= 2; i++) {
        char key[20];
        char value[20];

        snprintf(key, sizeof(key), "bssid%u", i);
        snprintf(value, sizeof(value), "00:00:00:00:00:%02u", i);
        set_value_for_key(key, value);
        if (i == 2) {
            snprintf(key, sizeof(key), "ssid%u", i);
            snprintf(value, sizeof(value), "SSID_%u", i);
            set_value_for_key(key, value);
        }
        snprintf(key, sizeof(key), "pass%u", i);
        snprintf(value, sizeof(value), "PASSWORD_%u", i);
        set_value_for_key(key, value);
    }
    step_state_machine();

    // GIVEN the SCANNING state with ssid1 not found
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);
    // WHEN a known BSSID is found
    cyw43_ev_scan_result_t scan_result;
    memset(&scan_result, 0, sizeof(scan_result));
    scan_result.bssid[5] = 1; // bssid1 (00:00:00:00:00:01)
    scan_callback(NULL, &scan_result);
    // THEN SSID marked as found
    ASSERT(g_wifi_state.ssid_scan_info[1] == FOUND);
    ASSERT(strcmp(wifi_settings_get_ssid_status(1), "FOUND") == 0);

    // GIVEN the SCANNING state with bssid2 not found
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);
    ASSERT(g_wifi_state.ssid_scan_info[2] == NOT_FOUND);
    // WHEN known SSID_2 is found, but the BSSID is also listed and is different
    memset(&scan_result, 0, sizeof(scan_result));
    scan_result.bssid[5] = 0x99; // unknown BSSID (00:00:00:00:00:99)
    strcpy((char*)scan_result.ssid, "SSID_2");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    // THEN ssid2 is still not marked as found, as the BSSID check takes priority
    ASSERT(g_wifi_state.ssid_scan_info[2] == NOT_FOUND);

    // GIVEN the SCANNING state with bssid2 not found
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);
    ASSERT(g_wifi_state.ssid_scan_info[2] == NOT_FOUND);
    // WHEN unknown SSID is found, but the BSSID is bssid2
    memset(&scan_result, 0, sizeof(scan_result));
    scan_result.bssid[5] = 2; // bssid2 (00:00:00:00:00:02)
    strcpy((char*)scan_result.ssid, "UnknownSSID");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    // THEN bssid2 is marked as found
    ASSERT(g_wifi_state.ssid_scan_info[2] == FOUND);

    // GIVEN that scanning ends
    mock_state = MS_DOWN;
    // WHEN periodic callback runs
    step_state_machine();
    // THEN begin_connecting() is called, state changes to CONNECTING,
    // connection begins to bssid1 (highest priority of those found)
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(strcmp(connected_ssid, "") == 0);  // No SSID is known (or used)
    ASSERT(memcmp("\x00\x00\x00\x00\x00\x01", connected_bssid, WIFI_BSSID_SIZE) == 0); // bssid1
    ASSERT(strcmp(connected_password, "PASSWORD_1") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 1);
    ASSERT(g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] == ATTEMPT);
    ASSERT(mock_state == MS_JOIN);

    // GIVEN connecting state, connection fails
    current_link_status = CYW43_LINK_DOWN;
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as FAILED
    ASSERT(g_wifi_state.ssid_scan_info[1] == FAILED);
    ASSERT(strcmp(wifi_settings_get_ssid_status(1), "FAILED") == 0);

    // GIVEN scanning state
    ASSERT(g_wifi_state.cstate == SCANNING);

    // WHEN periodic callback runs
    step_state_machine();

    // THEN after forcing a disconnect, and finding that no scan is active, a new connection begins
    // to bssid2
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(g_wifi_state.selected_ssid_index == 2);
    ASSERT(g_wifi_state.ssid_scan_info[2] == ATTEMPT);
    ASSERT(strcmp(wifi_settings_get_ssid_status(2), "ATTEMPT") == 0);
    ASSERT(memcmp("\x00\x00\x00\x00\x00\x02", connected_bssid, WIFI_BSSID_SIZE) == 0); // bssid2
    ASSERT(strcmp(connected_ssid, "") == 0);  // SSID_2 is not used for the connection attempt
    ASSERT(strcmp(connected_password, "PASSWORD_2") == 0);
    ASSERT(mock_state == MS_JOIN);
}

void test_wifi_connecting_with_open_hotspot() {
    // GIVEN the end of a scan, in which the only hotspot which was found is one
    // which has been configured without a password
    reset_for_state_machine_test();
    set_value_for_key("ssid1", "SSID_1");
    step_state_machine();
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);
    cyw43_ev_scan_result_t scan_result;
    memset(&scan_result, 0, sizeof(scan_result));
    strcpy((char*)scan_result.ssid, "SSID_1");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN begin_connecting() is called, state changes to CONNECTING,
    // connection begins to ssid1, with no password, and open authentication mode
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(strcmp(connected_ssid, "SSID_1") == 0);
    ASSERT(strcmp(connected_password, "") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 1);
    ASSERT(mock_state == MS_JOIN);
}

void test_wifi_connecting_with_multiple_passwords_for_ssid() {
    // GIVEN the end of a scan, in which only one SSID was recognised, and it's
    // defined many times in the configuration, with different passwords (user is
    // not sure which password is currently in use?)
    reset_for_state_machine_test();
    for (uint i = 1; i <= MAX_NUM_SSIDS; i++) {
        char key[20];
        char value[20];

        snprintf(key, sizeof(key), "ssid%u", i);
        set_value_for_key(key, "SSID_X");
        snprintf(key, sizeof(key), "pass%u", i);
        snprintf(value, sizeof(value), "PASSWORD_%u", i);
        set_value_for_key(key, value);
    }
    step_state_machine();
    ASSERT(g_wifi_state.cstate == SCANNING);
    ASSERT(scan_callback);
    cyw43_ev_scan_result_t scan_result;
    memset(&scan_result, 0, sizeof(scan_result));
    strcpy((char*)scan_result.ssid, "SSID_X");
    scan_result.ssid_len = (uint8_t) strlen((char*)scan_result.ssid);
    scan_callback(NULL, &scan_result);
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN begin_connecting() is called, to ssid1, with pass1,
    // but all of the other entries are available for connection too.
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(strcmp(connected_ssid, "SSID_X") == 0);
    ASSERT(strcmp(connected_password, "PASSWORD_1") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 1);
    ASSERT(g_wifi_state.ssid_scan_info[1] == ATTEMPT);
    ASSERT(strcmp(wifi_settings_get_ssid_status(1), "ATTEMPT") == 0);
    for (uint i = 2; i <= MAX_NUM_SSIDS; i++) {
        ASSERT(g_wifi_state.ssid_scan_info[i] == FOUND);
        ASSERT(strcmp(wifi_settings_get_ssid_status(i), "FOUND") == 0);
    }

    // GIVEN connection fails with a bad password
    current_link_status = CYW43_LINK_BADAUTH;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN state changes to SCANNING and the SSID is marked as BADAUTH
    ASSERT(g_wifi_state.ssid_scan_info[1] == BADAUTH);
    ASSERT(strcmp(wifi_settings_get_ssid_status(1), "BADAUTH") == 0);
    ASSERT(g_wifi_state.cstate == SCANNING);

    // GIVEN connection attempt ends
    mock_state = MS_DOWN;

    // WHEN periodic callback runs
    step_state_machine();

    // THEN begin_connecting() is called again, this time for ssid2 with pass2.
    ASSERT(g_wifi_state.cstate == CONNECTING);
    ASSERT(strcmp(connected_ssid, "SSID_X") == 0);
    ASSERT(strcmp(connected_password, "PASSWORD_2") == 0);
    ASSERT(g_wifi_state.selected_ssid_index == 2);
    ASSERT(g_wifi_state.ssid_scan_info[2] == ATTEMPT);
    ASSERT(strcmp(wifi_settings_get_ssid_status(2), "ATTEMPT") == 0);
}

void test_wifi_settings_get_connect_status_text() {
    int ret;

    // GIVEN uninitialised state
    reset_all();
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message with '\0' termination
    ASSERT(strstr(text_buffer, "uninitialised"));
    ASSERT(ret > 0);
    ASSERT(ret == (int) strlen(text_buffer));

    // GIVEN uninitialised state but with a small buffer
    reset_all();
    const int tiny_buffer_size = 5;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, tiny_buffer_size);
    // THEN the output is truncated appropriately, with a return value indicating
    // how much space was required (like snprintf)
    ASSERT(ret > tiny_buffer_size);
    ASSERT((int) strlen(text_buffer) == (tiny_buffer_size - 1));
    ASSERT(text_buffer[tiny_buffer_size - 1] == '\0');
    ASSERT(text_buffer[tiny_buffer_size] == TEXT_BUFFER_FILL_BYTE);

    // GIVEN initialisation error state
    reset_all();
    g_wifi_state.cstate = INITIALISATION_ERROR;
    g_wifi_state.hw_error_code = 123;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "init error: 123"));

    // GIVEN storage empty error state
    reset_all();
    g_wifi_state.cstate = STORAGE_EMPTY_ERROR;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "No WiFi details have been stored"));

    // GIVEN disconnected state
    reset_all();
    g_wifi_state.cstate = DISCONNECTED;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "disconnected"));

    // GIVEN an unknown state e.g. corrupted memory
    reset_all();
    g_wifi_state.cstate = -1;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "unknown (-1)"));

    // GIVEN try to connect state
    reset_all();
    g_wifi_state.cstate = TRY_TO_CONNECT;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "did not find any known"));

    // GIVEN scanning state
    reset_all();
    g_wifi_state.cstate = SCANNING;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "scanning for"));

    // GIVEN connecting state, with an SSID that isn't defined
    reset_all();
    g_wifi_state.cstate = CONNECTING;
    g_wifi_state.selected_ssid_index = 9;
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message
    ASSERT(strstr(text_buffer, "connecting to ssid9=?"));

    // GIVEN connecting state, with a BSSID and SSID defined
    reset_all();
    g_wifi_state.cstate = CONNECTING;
    g_wifi_state.selected_ssid_index = 9;
    set_value_for_key("ssid9", "Ignore");
    set_value_for_key("bssid9", "01:02:03:04:05:06");
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message showing the BSSID
    ASSERT(strstr(text_buffer, "connecting to bssid9=01:02:03:04:05:06"));

    // GIVEN connected state, with a SSID defined
    reset_all();
    g_wifi_state.cstate = CONNECTED_IP;
    g_wifi_state.selected_ssid_index = 9;
    set_value_for_key("ssid9", "Test");
    // WHEN wifi_settings_get_connect_status_text is called
    ret = wifi_settings_get_connect_status_text(text_buffer, sizeof(text_buffer));
    // THEN it prints a suitable message showing the BSSID
    ASSERT(strstr(text_buffer, "connected to ssid9=Test"));
}

void test_wifi_settings_get_hw_status_text() {
    int ret;

    // GIVEN uninitialised state
    reset_all();

    // WHEN wifi_settings_get_hw_status_text is called
    ret = wifi_settings_get_hw_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN output is an empty string
    ASSERT(ret == (int) strlen(text_buffer));
    ASSERT(ret == 0);

    // GIVEN disconnected state 
    reset_for_state_machine_test();

    // WHEN wifi_settings_get_hw_status_text is called
    ret = wifi_settings_get_hw_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN a suitable message is printed
    ASSERT(ret == (int) strlen(text_buffer));
    ASSERT(strstr(text_buffer, "CYW43_LINK_DOWN"));
    ASSERT(strstr(text_buffer, "scan_active = False"));

    // GIVEN connecting state 
    reset_for_state_machine_test();
    current_link_status = CYW43_LINK_JOIN;

    // WHEN wifi_settings_get_hw_status_text is called
    ret = wifi_settings_get_hw_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN a suitable message is printed
    ASSERT(ret == (int) strlen(text_buffer));
    ASSERT(strstr(text_buffer, "CYW43_LINK_JOIN"));

    // GIVEN scanning state
    reset_for_state_machine_test();
    mock_state = MS_SCANNING;

    // WHEN wifi_settings_get_hw_status_text is called
    ret = wifi_settings_get_hw_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN a suitable message is printed
    ASSERT(strstr(text_buffer, "CYW43_LINK_DOWN"));
    ASSERT(strstr(text_buffer, "scan_active = True"));
}

void test_wifi_settings_get_ip_status_text() {
    int ret;

    // GIVEN uninitialised state
    reset_all();

    // WHEN wifi_settings_get_ip_status_text is called
    ret = wifi_settings_get_ip_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN output is an empty string
    ASSERT(ret == (int) strlen(text_buffer));
    ASSERT(ret == 0);

    // GIVEN connected IP state
    reach_connected_ip_state();

    // WHEN wifi_settings_get_ip_status_text is called
    ret = wifi_settings_get_ip_status_text(text_buffer, sizeof(text_buffer));
    
    // THEN a suitable message is printed
    ASSERT(ret == (int) strlen(text_buffer));
    ASSERT(strstr(text_buffer, "IPv4 address = 0.0.0.1"));
}

void test_wifi_settings_has_no_wifi_details() {
    bool ret;

    // GIVEN uninitialised state
    reset_all();

    // WHEN wifi_settings_has_no_wifi_details() is called
    ret = wifi_settings_has_no_wifi_details();
    
    // THEN returns true
    ASSERT(ret);

    // GIVEN some SSID
    reset_all();
    create_ssids(1);

    // WHEN wifi_settings_has_no_wifi_details() is called
    ret = wifi_settings_has_no_wifi_details();
    
    // THEN returns false
    ASSERT(!ret);
}

int main() {
    test_wifi_settings_init();
    test_wifi_settings_deinit();
    test_wifi_settings_connect();
    test_wifi_settings_disconnect();
    test_wifi_settings_is_connected();
    test_wifi_storage_empty_state();
    test_wifi_connecting_state();
    test_wifi_connected_ip_state();
    test_wifi_connecting_state_when_lost();
    test_wifi_connecting_state_when_ssid_details_are_forgotten();
    test_wifi_connecting_with_bssid();
    test_wifi_connecting_with_open_hotspot();
    test_wifi_connecting_with_multiple_passwords_for_ssid();
    test_wifi_settings_get_connect_status_text();
    test_wifi_settings_get_hw_status_text();
    test_wifi_settings_get_ip_status_text();
    test_wifi_settings_has_no_wifi_details();
    return 0;
}
