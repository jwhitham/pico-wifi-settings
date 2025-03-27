/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * DNS lookup helper function
 */

#ifndef DNS_LOOKUP_H
#define DNS_LOOKUP_H

#include "lwip/ip.h"

bool dns_lookup(const char* input_address, ip_addr_t* output_address);

#endif
