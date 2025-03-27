/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This is a minimal lwip-like API which uses the host's sockets library.
 *
 */

#include "remote_virtual.h"
#include "lwip/tcp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define NUM_PCBS                20
#define WRITE_BUFFER_SIZE       1024
#define READ_BUFFER_SIZE        1024

typedef enum pcb_type_t {
    FREE = 0,
    ALLOCATED,
    PORT,
    LISTEN,
    ACTIVE,
} pcb_type_t;

struct callbacks_t {
    void *arg;
    tcp_accept_fn accept;
    tcp_recv_fn recv;
    tcp_sent_fn sent;
    tcp_err_fn err;
};

struct tcp_pcb {
    pcb_type_t pcb_type;
    int socket;
    struct callbacks_t callbacks;
    uint16_t outstanding_write_size;
};


static struct tcp_pcb g_pcbs[NUM_PCBS];

static struct tcp_pcb* allocate_pcb() {
    for (uint32_t i = 0; i < NUM_PCBS; i++) {
        struct tcp_pcb* pcb = &g_pcbs[i];
        if (pcb->pcb_type == FREE) {
            memset(pcb, 0, sizeof(struct tcp_pcb));
            pcb->pcb_type = ALLOCATED;
            return pcb;
        }
    }
    return NULL;
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
        struct tcp_pcb* a_pcb = allocate_pcb();
        ASSERT(a_pcb);
        a_pcb->pcb_type = ACTIVE;
        a_pcb->socket = a_socket;
        ASSERT(pcb->callbacks.accept);
        memcpy(&a_pcb->callbacks, &pcb->callbacks, sizeof(struct callbacks_t));
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
            struct pbuf p;
            p.payload = buffer;
            p.len = (uint16_t) rc;
            if (pcb->callbacks.recv(
                    pcb->callbacks.arg, pcb, &p, ERR_OK) != ERR_OK) {
                tcp_close(pcb);
            }
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
        ASSERT(pcb->outstanding_write_size >= size);
        pcb->outstanding_write_size -= size;
        return true;
    }
    return false;
}

bool fake_lwip_loop() {
    bool activity = false;
    for (uint i = 0; i < NUM_PCBS; i++) {
        struct tcp_pcb* pcb = &g_pcbs[i];
        switch (pcb->pcb_type) {
            case FREE:
            case PORT:
                // No poll action required
                break;
            case LISTEN:
                activity = process_listen(pcb) || activity;
                break;
            case ACTIVE:
                activity = process_read(pcb) || activity;
                activity = process_write(pcb) || activity;
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
        if (pcb->pcb_type == ACTIVE) {
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
    ASSERT(pcb->pcb_type == ACTIVE);
    return (uint16_t) WRITE_BUFFER_SIZE - pcb->outstanding_write_size;
}

err_t tcp_write(struct tcp_pcb *pcb, const void *dataptr, u16_t len, u8_t apiflags) {
    ASSERT(pcb);
    ASSERT(apiflags == TCP_WRITE_FLAG_COPY);
    ASSERT(pcb->pcb_type == ACTIVE);

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
    struct tcp_pcb* pcb = allocate_pcb();
    pcb->socket = socket(AF_INET, SOCK_STREAM, 0);
    ASSERT(pcb->socket >= 0);
    pcb->pcb_type = PORT;
    return pcb;
}

err_t tcp_bind(struct tcp_pcb *pcb, const ip_addr_t *ipaddr, u16_t port) {
    ASSERT(pcb);
    ASSERT(ipaddr == NULL);
    ASSERT(pcb->socket >= 0);
    ASSERT(pcb->pcb_type == PORT);

    int enable = 1;
    int rc = setsockopt(pcb->socket, SOL_SOCKET,
            SO_REUSEADDR, &enable, sizeof(enable));
    ASSERT(rc == 0);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    rc = bind(pcb->socket, (const struct sockaddr*) &addr, sizeof(addr));
    ASSERT(rc == 0);

    return ERR_OK;
}

struct tcp_pcb* tcp_listen_with_backlog(struct tcp_pcb *pcb, u8_t backlog) {
    ASSERT(pcb);

    struct tcp_pcb* service_pcb = allocate_pcb();
    ASSERT(pcb->socket >= 0);
    ASSERT(pcb->pcb_type == PORT);
    service_pcb->socket = pcb->socket;
    pcb->socket = -1;
    int rc = listen(service_pcb->socket, backlog);
    ASSERT(rc == 0);
    service_pcb->pcb_type = LISTEN;
    return service_pcb;
}

void tcp_arg(struct tcp_pcb *pcb, void *arg) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == ACTIVE);
    pcb->callbacks.arg = arg;
}

void tcp_accept(struct tcp_pcb *pcb, tcp_accept_fn accept) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == LISTEN);
    pcb->callbacks.accept = accept;
}

void tcp_recv(struct tcp_pcb *pcb, tcp_recv_fn recv) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == ACTIVE);
    pcb->callbacks.recv = recv;
}

void tcp_sent(struct tcp_pcb *pcb, tcp_sent_fn sent) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == ACTIVE);
    pcb->callbacks.sent = sent;
}

void tcp_err(struct tcp_pcb *pcb, tcp_err_fn err) {
    ASSERT(pcb);
    ASSERT(pcb->pcb_type == ACTIVE);
    pcb->callbacks.err = err;
}
