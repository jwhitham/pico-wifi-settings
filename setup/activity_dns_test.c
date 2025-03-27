/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test the DNS connection
 */


#include "activity_dns_test.h"
#include "user_interface.h"
#include "dns_lookup.h"

#include <stdio.h>
#include <string.h>


static char g_lookup_address[MAX_EDIT_LINE_LENGTH];

void activity_dns_test() {
    ui_clear();
    printf("Please enter a host name to look up:\n");
    if (strlen(g_lookup_address) == 0) {
        strcpy(g_lookup_address, "example.com");
    }
    if ((!ui_text_entry(g_lookup_address, sizeof(g_lookup_address))) || (strlen(g_lookup_address) == 0)) {
        return; // cancel
    }

    printf("Sending request...\n");

    ip_addr_t addr;
    if (!dns_lookup(g_lookup_address, &addr)) {
        printf("%s was not found\n", g_lookup_address);
    } else {
        // Decode the address
        char addr_str[IP4ADDR_STRLEN_MAX + 1];
        addr_str[0] = '\0';
        ipaddr_ntoa_r(&addr, addr_str, sizeof(addr_str));
        printf("%s is %s\n", g_lookup_address, addr_str);
    }
    ui_wait_for_the_user();
}
