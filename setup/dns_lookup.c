/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * DNS lookup helper function
 */


#include "dns_lookup.h"

#include "lwip/dns.h"

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"


typedef struct dns_data_t {
    ip_addr_t*  output_address;
    bool        finished, success;
} dns_data_t;

static void dns_found(const char *hostname, const ip_addr_t *ipaddr, void *arg) { 
    dns_data_t* dns_data = (dns_data_t*) arg;
    if (ipaddr) {
        memcpy(dns_data->output_address, ipaddr, sizeof(ip_addr_t));
        dns_data->success = true;
    }
    dns_data->finished = true;
}

bool dns_lookup(const char* input_address, ip_addr_t* output_address) {
    memset(output_address, 0, sizeof(ip_addr_t));

    dns_data_t dns_data;
    memset(&dns_data, 0, sizeof(dns_data));
    dns_data.output_address = output_address;

    cyw43_arch_lwip_begin();
    err_t err = dns_gethostbyname_addrtype(input_address, output_address,
                        dns_found, &dns_data, LWIP_DNS_ADDRTYPE_IPV4);
    cyw43_arch_lwip_end();

    if (err == ERR_OK) {
        // Result available already (IP address or cached)
        return true;

    } else if (err == ERR_INPROGRESS) {
        // Wait for callback to dns_found (can't cancel this; eventually LWIP will time out)
        while (!dns_data.finished) {
            sleep_ms(10);
        }
        return dns_data.success;
    } else {
        // Unreachable DNS server / invalid hostname / other error
        return false;
    }
}
