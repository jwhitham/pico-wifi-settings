/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test the connection with ping (ICMP)
 */


#include "activity_ping.h"
#include "user_interface.h"
#include "dns_lookup.h"

#include "lwip/opt.h"

#if !LWIP_RAW
#error "LWIP_RAW is required"
#endif

#include "lwip/icmp.h"
#include "lwip/raw.h"
#include "lwip/inet_chksum.h"

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include <stdio.h>
#include <string.h>

#define PING_DATA_SIZE      24
#define IPV4_ADDRESS_SIZE   (IP4ADDR_STRLEN_MAX + 1)
#define IN_FLIGHT_MASK_SIZE 7

static char g_ping_address[IPV4_ADDRESS_SIZE];

typedef union ping_t {
    struct icmp_echo_hdr    header;
    uint8_t                 bytes[sizeof(struct icmp_echo_hdr) + PING_DATA_SIZE];
} ping_t;

typedef struct ping_data_t {
    uint32_t                send_time;
    uint16_t                seq_num;
    uint16_t                ping_id;
    uint                    in_flight;
    uint                    lost_counter;
} ping_data_t;


// This is based on the LWIP example contrib/apps/ping/ping.c
static err_t ping_send(ping_data_t* ping_data, struct raw_pcb *raw, const ip_addr_t *addr) {
    struct pbuf *p;
    err_t err = ERR_MEM;

    p = pbuf_alloc(PBUF_IP, (u16_t)sizeof(ping_t), PBUF_RAM);
    if (p) {
        if ((p->len == p->tot_len) && (p->next == NULL)) {
            ping_t* ping = (ping_t *)p->payload;

            // create packet
            memset(ping, 0, sizeof(ping_t));
            ICMPH_TYPE_SET(&ping->header, ICMP_ECHO);
            ICMPH_CODE_SET(&ping->header, 0);
            ping->header.chksum = 0;
            ping->header.id = ping_data->ping_id;
            ping->header.seqno = lwip_htons(ping_data->seq_num);
            ping->header.chksum = inet_chksum(&ping->header, sizeof(ping_t));

            // send
            err = raw_sendto(raw, p, addr);
            ping_data->send_time = time_us_32();
            ping_data->seq_num++;

            // set "in flight" for each packet that's out there
            const uint32_t mask = 1 << (ping_data->seq_num & IN_FLIGHT_MASK_SIZE);
            if (ping_data->in_flight & mask) {
                // The bit should have been cleared - it wasn't. A packet was lost.
                ping_data->lost_counter ++;
            } else {
                ping_data->in_flight |= mask;
            }
        }
        pbuf_free(p);
    }
    return err;
}

// This is based on the LWIP example contrib/apps/ping/ping.c
static u8_t ping_recv(void *arg, struct raw_pcb *, struct pbuf *p, const ip_addr_t *addr) {
    const uint32_t capture_time = time_us_32();
    ping_data_t* ping_data = (ping_data_t*) arg;
    int ttl = 0;

    // Read TTL from IP header
    if (p->tot_len >= PBUF_IP_HLEN) {
        ttl = IPH_TTL((struct ip_hdr *) p->payload);
    }

    // If possible, remove IP header and parse ICMP header
    if ((p->tot_len >= (PBUF_IP_HLEN + sizeof(struct icmp_echo_hdr)))
    && (pbuf_remove_header(p, PBUF_IP_HLEN) == 0)) {
        ping_t* ping = (ping_t *)p->payload;

        // Decode the address
        char source_addr_str[IPV4_ADDRESS_SIZE];
        source_addr_str[0] = '\0';
        ipaddr_ntoa_r(addr, source_addr_str, sizeof(source_addr_str));

        // Report the packet
        if ((p->tot_len == sizeof(ping_t))
        && (ICMPH_TYPE(&ping->header) == ICMP_ER)
        && (ping->header.id == ping_data->ping_id)) {
            uint16_t rx_seq_num = lwip_ntohs(ping->header.seqno);
            printf("%d bytes from %s: icmp_seq=%d ttl=%d time=%u ms\n",
                p->tot_len,
                source_addr_str,
                (int) rx_seq_num,
                ttl,
                (uint) (capture_time - ping_data->send_time) / 1000);

            // clear "in flight" bit when the reply is received
            const uint32_t mask = 1 << (ping_data->seq_num & IN_FLIGHT_MASK_SIZE);
            ping_data->in_flight &= ~mask;
        } else {
            printf("from %s: type %d code %d length %d\n",
                source_addr_str, ICMPH_TYPE(&ping->header),
                ICMPH_CODE(&ping->header), p->tot_len);
        }
        pbuf_free(p);
        fflush(stdout);
        return 1; // packet eaten
    }
    // not eaten, restore original packet
    pbuf_add_header(p, PBUF_IP_HLEN);
    return 0;
}


void activity_ping() {
    ui_clear();
    printf("Please enter an IP address or host name to ping:\n");
    if (strlen(g_ping_address) == 0) {
        if (netif_default) {
            ip4addr_ntoa_r(netif_ip4_gw(netif_default), g_ping_address, IPV4_ADDRESS_SIZE);
        }
    }
    if ((!ui_text_entry(g_ping_address, sizeof(g_ping_address))) || (strlen(g_ping_address) == 0)) {
        return; // cancel
    }

    ip_addr_t addr;
    if (!dns_lookup(g_ping_address, &addr)) {
        printf("Unable to resolve address\n");
        ui_wait_for_the_user();
        return;
    }
 
    cyw43_arch_lwip_begin();
    struct raw_pcb* ping_pcb = raw_new(IP_PROTO_ICMP);
    cyw43_arch_lwip_end();
    if (!ping_pcb) {
        printf("Unable to allocate raw socket\n");
        ui_wait_for_the_user();
        return;
    }

    ping_data_t ping_data;
    memset(&ping_data, 0, sizeof(ping_data));
    ping_data.seq_num = 1;
    ping_data.send_time = time_us_32();
    ping_data.ping_id = (uint16_t) ping_data.send_time;

    cyw43_arch_lwip_begin();
    raw_recv(ping_pcb, ping_recv, &ping_data);
    raw_bind(ping_pcb, IP_ADDR_ANY);
    cyw43_arch_lwip_end();

    printf("Press a key to stop pinging:\n");
    absolute_time_t next_ping_time = make_timeout_time_ms(0);
    uint previous = 0;
    while (getchar_timeout_us(100) < 0) {
        if (time_reached(next_ping_time)) {
            next_ping_time = delayed_by_ms(next_ping_time, 1000);
            cyw43_arch_lwip_begin();
            err_t err = ping_send(&ping_data, ping_pcb, &addr);
            cyw43_arch_lwip_end();
            if (err == ERR_RTE) {
                printf("Unable to send, no route to host\n");
            } else if (err != 0) {
                printf("Unable to send, err %d\n", err);
            } else if (ping_data.lost_counter != previous) {
                printf("%u packets sent with no reply\n", ping_data.lost_counter);
                previous = ping_data.lost_counter;
            }
        }
    }

    cyw43_arch_lwip_begin();
    raw_recv(ping_pcb, NULL, NULL);
    raw_remove(ping_pcb);
    cyw43_arch_lwip_end();
}
