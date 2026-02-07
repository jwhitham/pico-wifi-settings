/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This is a minimal lwip-like API which uses the host's sockets library.
 *
 */

#include "remote_virtual.h"
#include "lwip/common.h"
#include "lwip/pbuf.h"
#include "lwip/tcp.h"
#include "lwip/udp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define NUM_PCBS                20
#define NUM_PBUFS               20
#define WRITE_BUFFER_SIZE       1024
#define READ_BUFFER_SIZE        1024

typedef enum pcb_type_t {
    FREE = 0,       // not in use, not allocated
    ALLOCATED,      // ready for use
    TCP_PORT,       // ready to bind
    TCP_LISTEN,     // ready to listen
    TCP_ACTIVE,     // bound and either listening or connected
    UDP_PORT,       // ready to bind
    UDP_ACTIVE,     // bound
} pcb_type_t;

struct tcp_callbacks_t {
    void *arg;
    tcp_accept_fn accept;
    tcp_recv_fn recv;
    tcp_sent_fn sent;
    tcp_err_fn err;
};

struct udp_callbacks_t {
    void *arg;
    udp_recv_fn recv;
};

struct tcp_pcb {
    pcb_type_t pcb_type;
    int socket;
    struct tcp_callbacks_t callbacks;
    uint16_t outstanding_write_size;
    uint16_t received_size;
};

struct udp_pcb {
    pcb_type_t pcb_type;
    int socket;
    struct udp_callbacks_t callbacks;
};

union general_pcb {
    pcb_type_t pcb_type;
    struct tcp_pcb tcp;
    struct udp_pcb udp;
};


static union general_pcb g_pcbs[NUM_PCBS];
static struct pbuf g_pbufs[NUM_PBUFS];
static unsigned g_cyw43_arch_lwip_count;

static union general_pcb* allocate_pcb() {
    for (uint32_t i = 0; i < NUM_PCBS; i++) {
        union general_pcb* pcb = &g_pcbs[i];
        if (pcb->pcb_type == FREE) {
            memset(pcb, 0, sizeof(union general_pcb));
            pcb->pcb_type = ALLOCATED;
            return pcb;
        }
    }
    ASSERT(0);
    return NULL;
}

struct pbuf* pbuf_alloc(pbuf_layer layer, u16_t length, pbuf_type type)
{
    ASSERT(layer == PBUF_TRANSPORT);
    ASSERT(type == PBUF_RAM);
    for (uint32_t i = 0; i < NUM_PBUFS; i++) {
        struct pbuf* p = &g_pbufs[i];
        if (!p->payload) {
            p->payload = calloc(1, length);
            ASSERT(p->payload);
            p->len = length;
            return p;
        }
    }
    ASSERT(0);
    return NULL;
}

void pbuf_free(struct pbuf *p)
{
    free(p->payload);
    p->payload = NULL;
    p->len = 0;
}

static bool is_ready_for_read(int socket) {
    ASSERT(socket >= 0);
    struct pollfd fds[1];
    fds[0].fd = socket;
    fds[0].events = POLLIN | POLLERR;
    fds[0].revents = 0;
    if ((poll(fds, 1, 0) > 0) && fds[0].revents) {
        return true;
    }
    return false;
}

static bool process_listen(struct tcp_pcb* pcb) {
    if (is_ready_for_read(pcb->socket)) {
        // New connection
        int a_socket = accept(pcb->socket, NULL, NULL);
        ASSERT(a_socket >= 0);
        struct tcp_pcb* a_pcb = &allocate_pcb()->tcp;
        ASSERT(a_pcb);
        a_pcb->pcb_type = TCP_ACTIVE;
        a_pcb->socket = a_socket;
        ASSERT(pcb->callbacks.accept);
        memcpy(&a_pcb->callbacks, &pcb->callbacks, sizeof(struct tcp_callbacks_t));
        if (pcb->callbacks.accept(
                pcb->callbacks.arg, a_pcb, ERR_OK) != ERR_OK) {
            tcp_close(a_pcb);
        }
        return true;
    }
    return false;
}

static bool process_read(struct tcp_pcb* pcb) {
    if (is_ready_for_read(pcb->socket)) {
        // New data received
        uint8_t buffer[READ_BUFFER_SIZE];
        ssize_t rc = read(pcb->socket, buffer, sizeof(buffer));
        if (rc < 0) {
            // Problem with this socket
            ASSERT(pcb->callbacks.err);
            pcb->callbacks.err(pcb->callbacks.arg, ERR_ABRT);
            tcp_close(pcb);
        } else {
            // Data received
            ASSERT(pcb->callbacks.recv);
            ASSERT(rc <= sizeof(buffer));
            struct pbuf* p = pbuf_alloc(PBUF_TRANSPORT, rc, PBUF_RAM);
            ASSERT(p->payload);    // pbuf payload should have been allocated
            ASSERT(p->len == rc);
            memcpy(p->payload, buffer, p->len);
            pcb->received_size = 0;
            if (pcb->callbacks.recv(
                    pcb->callbacks.arg, pcb, p, ERR_OK) != ERR_OK) {
                tcp_close(pcb);
            } else {
                ASSERT(pcb->received_size == rc);
            }
            ASSERT(!p->payload);    // pbuf payload should have been freed
            ASSERT(!p->len);
        }
        return true;
    }
    return false;
}

static bool process_write(struct tcp_pcb* pcb) {
    uint16_t size = pcb->outstanding_write_size;
    if (size > 0) {
        ASSERT(pcb->callbacks.sent);
        if (pcb->callbacks.sent(
                pcb->callbacks.arg, pcb,
                size) != ERR_OK) {
            tcp_close(pcb);
        }
        if (pcb->pcb_type == FREE) {
            // closed - pcb is reset
            ASSERT(pcb->outstanding_write_size == 0);
        } else {
            // still open
            ASSERT(pcb->pcb_type == TCP_ACTIVE);
            ASSERT(pcb->outstanding_write_size >= size);
            pcb->outstanding_write_size -= size;
        }
        return true;
    }
    return false;
}

bool fake_lwip_loop() {
    bool activity = false;
    for (uint i = 0; i < NUM_PCBS; i++) {
        union general_pcb* pcb = &g_pcbs[i];
        switch (pcb->pcb_type) {
            case FREE:
            case TCP_PORT:
            case UDP_PORT:
                // No poll action required
                break;
            case TCP_LISTEN:
                activity = process_listen(&pcb->tcp) || activity;
                break;
            case TCP_ACTIVE:
                activity = process_read(&pcb->tcp) || activity;
                activity = process_write(&pcb->tcp) || activity;
                break;
            case UDP_ACTIVE:
                //activity = process_read(&pcb->udp) || activity;
                break;
            case ALLOCATED:
                // Should not be in this state
                ASSERT(false);
                break;
            default:
                ASSERT(false);
                break;
        }
    }
    return activity;
}

void tcp_abort(struct tcp_pcb *pcb) {
    ASSERT(pcb);
    if (pcb->socket >= 0) {
        if (pcb->pcb_type == TCP_ACTIVE) {
            shutdown(pcb->socket, SHUT_RDWR);
        }
        close(pcb->socket);
        pcb->socket = -1;
    }
}

err_t tcp_close(struct tcp_pcb *pcb) {
    ASSERT(pcb);
    tcp_abort(pcb);
    memset(pcb, 0, sizeof(struct tcp_pcb)); // pcb becomes FREE again
    return ERR_OK;
}

uint16_t tcp_sndbuf(struct tcp_pcb *pcb) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    return (uint16_t) WRITE_BUFFER_SIZE - pcb->outstanding_write_size;
}

err_t tcp_write(struct tcp_pcb *pcb, const void *dataptr, u16_t len, u8_t apiflags) {
    ASSERT(pcb);
    ASSERT(apiflags == TCP_WRITE_FLAG_COPY);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);

    uint16_t available_write_space =
        (uint16_t) WRITE_BUFFER_SIZE - pcb->outstanding_write_size;
    if (available_write_space < len) {
        // Not enough fake LWIP buffer space
        // (Actually, the buffer is just simulated - data is always written)
        return ERR_MEM;
    }

    ssize_t check = write(pcb->socket, dataptr, len);
    ASSERT(check == len);
    pcb->outstanding_write_size += len;
    return ERR_OK;
}


struct tcp_pcb* tcp_new_ip_type(u8_t type) {
    ASSERT(type == IPADDR_TYPE_ANY);
    struct tcp_pcb* pcb = &allocate_pcb()->tcp;
    pcb->socket = socket(AF_INET, SOCK_STREAM, 0);
    ASSERT(pcb->socket >= 0);
    pcb->pcb_type = TCP_PORT;
    return pcb;
}

static err_t general_bind(int socket, const ip_addr_t *ipaddr, u16_t port) {
    ASSERT(ipaddr == NULL);
    ASSERT(socket >= 0);

    int enable = 1;
    int rc = setsockopt(socket, SOL_SOCKET,
            SO_REUSEADDR, &enable, sizeof(enable));
    ASSERT(rc == 0);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    rc = bind(socket, (const struct sockaddr*) &addr, sizeof(addr));
    ASSERT(rc == 0);

    return ERR_OK;
}

err_t tcp_bind(struct tcp_pcb *pcb, const ip_addr_t *ipaddr, u16_t port) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_PORT);
    return general_bind(pcb->socket, ipaddr, port);
}

struct tcp_pcb* tcp_listen_with_backlog(struct tcp_pcb *pcb, u8_t backlog) {
    ASSERT(pcb);

    struct tcp_pcb* service_pcb = &allocate_pcb()->tcp;
    ASSERT(pcb->socket >= 0);
    ASSERT(pcb->pcb_type == TCP_PORT);
    service_pcb->socket = pcb->socket;
    pcb->socket = -1;
    int rc = listen(service_pcb->socket, backlog);
    ASSERT(rc == 0);
    service_pcb->pcb_type = TCP_LISTEN;
    return service_pcb;
}

void tcp_arg(struct tcp_pcb *pcb, void *arg) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    pcb->callbacks.arg = arg;
}

void tcp_accept(struct tcp_pcb *pcb, tcp_accept_fn accept) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_LISTEN);
    pcb->callbacks.accept = accept;
}

void tcp_recv(struct tcp_pcb *pcb, tcp_recv_fn recv) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    pcb->callbacks.recv = recv;
}

void tcp_sent(struct tcp_pcb *pcb, tcp_sent_fn sent) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    pcb->callbacks.sent = sent;
}

void tcp_err(struct tcp_pcb *pcb, tcp_err_fn err) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    pcb->callbacks.err = err;
}

void tcp_recved(struct tcp_pcb *pcb, u16_t len) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == TCP_ACTIVE);
    pcb->received_size += len;
}

struct udp_pcb* udp_new_ip_type(u8_t type) {
    ASSERT(type == IPADDR_TYPE_ANY);
    struct udp_pcb* pcb = &allocate_pcb()->udp;
    pcb->socket = socket(AF_INET, SOCK_DGRAM, 0);
    ASSERT(pcb->socket >= 0);
    pcb->pcb_type = UDP_PORT;
    return pcb;
}

err_t udp_bind(struct udp_pcb* pcb, const ip_addr_t* ipaddr, u16_t port) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == UDP_PORT);
    return general_bind(pcb->socket, ipaddr, port);
}

err_t udp_sendto(struct udp_pcb* pcb, struct pbuf* p, const ip_addr_t* dst_ip, u16_t dst_port) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == UDP_ACTIVE);
    ASSERT(p->payload);
    ASSERT(!dst_ip);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(dst_port);
    addr.sin_addr.s_addr = dst_ip->addr;

    ssize_t check = sendto(pcb->socket, p->payload, p->len, 0,
                        (const struct sockaddr*) &addr, sizeof(addr));
    ASSERT(check == p->len);
    pbuf_free(p);
    return ERR_OK;
}

void udp_recv(struct udp_pcb* pcb, udp_recv_fn recv, void * recv_arg) {
    ASSERT(pcb);
    ASSERT((pcb->pcb_type == UDP_ACTIVE) || (pcb->pcb_type == UDP_PORT));
    pcb->callbacks.recv = recv;
}

void cyw43_arch_lwip_begin(void)
{
    g_cyw43_arch_lwip_count++;
}

void cyw43_arch_lwip_end(void)
{
    ASSERT(g_cyw43_arch_lwip_count > 0);
    g_cyw43_arch_lwip_count--;
}

