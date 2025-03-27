/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Test TCP connection, like telnet
 */


#include "activity_telnet_test.h"
#include "user_interface.h"
#include "dns_lookup.h"

#include "lwip/tcp.h"

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include <stdio.h>
#include <string.h>


static char g_telnet_address[MAX_EDIT_LINE_LENGTH];
static char g_telnet_port[6];

#define SEND_BUFFER_MASK        ((1 << 10) - 1)
#define SEND_BUFFER_SIZE        (SEND_BUFFER_MASK + 1)
#define SEND_PACKET_MAX_SIZE    500
#define FORCE_SEND_THRESHOLD    SEND_PACKET_MAX_SIZE
#define CONTROL_ESC             0x1d // control+]

typedef enum {
    NO_COMMAND, IAC_COMMAND,
    WILL_COMMAND, WONT_COMMAND, DO_COMMAND, DONT_COMMAND,
    SUBOPTION,
} state_t;

typedef struct telnet_data_t {
    struct tcp_pcb* tcp_pcb;
    char            send_buffer[SEND_BUFFER_SIZE];
    uint            send_buffer_write_index;
    uint            send_buffer_read_index;
    bool            finish;
    bool            send_in_progress;
    state_t         state; 
} telnet_data_t;

static uint send_buffer_get_count(telnet_data_t* telnet_data) {
    return (telnet_data->send_buffer_write_index -
            telnet_data->send_buffer_read_index) & SEND_BUFFER_MASK;
}

static void send_buffer_add_byte(telnet_data_t* telnet_data, uint8_t byte) {
    if (send_buffer_get_count(telnet_data) < SEND_BUFFER_MASK) {
        telnet_data->send_buffer[
                telnet_data->send_buffer_write_index & SEND_BUFFER_MASK] = byte;
        telnet_data->send_buffer_write_index =
                (telnet_data->send_buffer_write_index + 1) & SEND_BUFFER_MASK;
    }
}

static void send_buffer_remove_bytes(telnet_data_t* telnet_data, uint remove_count) {
    const uint in_buffer_count = send_buffer_get_count(telnet_data);
    if (remove_count > in_buffer_count) {
        // Removing more characters than are in the buffer? Should not happen, be defensive.
        remove_count = in_buffer_count;
    }
    telnet_data->send_buffer_read_index =
            (telnet_data->send_buffer_read_index + remove_count) & SEND_BUFFER_MASK;
}

static void telnet_client_close(struct tcp_pcb* tcp_pcb) {
    if (tcp_pcb != NULL) {
        // disable all callbacks
        tcp_arg(tcp_pcb, NULL);
        tcp_sent(tcp_pcb, NULL);
        tcp_recv(tcp_pcb, NULL);
        tcp_err(tcp_pcb, NULL);
        // close
        tcp_close(tcp_pcb);
    }
}

static void telnet_client_try_to_send_more_bytes(telnet_data_t* telnet_data) {
    const uint in_buffer_count = send_buffer_get_count(telnet_data);

    // Don't go further if
    // * there's nothing to send
    // * sending is already in progress (waiting for ACK)
    // * connection has been closed
    if ((in_buffer_count == 0) || telnet_data->finish || telnet_data->send_in_progress) {
        return;
    }
    // try to send as many bytes as possible - size is limited by the buffer count
    uint send_size = in_buffer_count;
    // and size may be limited by the number of contiguous bytes left in the buffer
    const uint contiguous_count = SEND_BUFFER_SIZE - (telnet_data->send_buffer_read_index & SEND_BUFFER_MASK);
    if (send_size > contiguous_count) {
        send_size = contiguous_count;
    }
    // and size may be limited by a fixed maximum
    if (send_size > SEND_PACKET_MAX_SIZE) {
        send_size = SEND_PACKET_MAX_SIZE;
    }
    err_t err = tcp_write(telnet_data->tcp_pcb,
            &telnet_data->send_buffer[telnet_data->send_buffer_read_index & SEND_BUFFER_MASK],
            send_size, 0);
    if (err == ERR_OK) {
        telnet_data->send_in_progress = true;
    } else {
        printf("\nDisconnected, write error %d\n", err);
        telnet_data->finish = true;
    }
}

static err_t telnet_client_sent(void *arg, struct tcp_pcb *tcp_pcb, u16_t len) {
    // Called when a packet is sent, and so there is more space is the output buffer,
    // possibly allowing more data to be sent.
    //
    // This callback:
    // * may call tcp_close
    // * must return ERR_OK
    // * might be called with arg == NULL (in which case tcp_close is correct behaviour)
    telnet_data_t* telnet_data = (telnet_data_t*)arg;
    if (!telnet_data) {
        telnet_client_close(tcp_pcb);
    } else {
        telnet_data->send_in_progress = false;
        send_buffer_remove_bytes(telnet_data, len);
        telnet_client_try_to_send_more_bytes(telnet_data);
    }
    return ERR_OK;
}

static err_t telnet_client_connected(void *arg, struct tcp_pcb*, err_t err) {
    // Called when connected - or if there is a connection error
    telnet_data_t* telnet_data = (telnet_data_t*)arg;
    if (!telnet_data) {
        // Be defensive (no action possible in this case)
        return ERR_OK;
    } else if (err != ERR_OK) {
        printf("Connection failed, callback error = %d\n", err);
        telnet_data->finish = true;
        return ERR_OK;
    } else {
        printf("Use control+] to disconnect\n");
        fflush(stdout);
        return ERR_OK;
    }
}

static void telnet_client_err(void*, err_t) {
    // Called if there is a TCP error with the connection or from the remote side.
    // This callback:
    // * must free the arg pointer (if not NULL and allocated on the heap) - in this case
    //   telnet_data_t is allocated on the stack so it does not need to be freed.
    // * should ignore the err parameter
    // * might be called with arg == NULL
    // Therefore, no action
}


static err_t telnet_client_recv(void *arg, struct tcp_pcb *tcp_pcb, struct pbuf *p, err_t err) {
    // Called when a packet is received or when the connection is closed by the other side
    //
    // The lwip documentation isn't clear about the expected behaviour for the tcp_recv callback,
    // but based on looking at lwip examples such as netio.c, tcpecho_raw.c, smtp.c, httpd.c,
    // the tcp_recv callback:
    // * must free the pbuf (p) if p != NULL
    // * must call tcp_recved to indicate how many bytes were received
    // * may call tcp_close
    // * can ignore the err parameter
    // * must return either ERR_OK or ERR_ABRT
    //   * even if called with err != ERR_OK - lwip examples generally just ignore this
    //   * if returning ERR_ABRT, there are special requirements:
    //     it must first call tcp_abort and free any session data.
    // * will be called with p == NULL if the remote side closed the connection,
    //   and in this case it should call tcp_close
    // * might be called with arg == NULL (in which case tcp_close is correct behaviour)
    telnet_data_t* telnet_data = (telnet_data_t*)arg;
    if ((!p) || (!telnet_data)) {
        if (p) {
            pbuf_free(p);
        }
        if (telnet_data) {
            if (!telnet_data->finish) {
                if (err) {
                    printf("\nDisconnected, read err %d\n", err);
                } else {
                    printf("\nDisconnected\n");
                }
                telnet_data->finish = true;
            }
            telnet_data->tcp_pcb = NULL;
        }
        telnet_client_close(tcp_pcb);
        return ERR_OK;
    }

    const uint payload_size = p->tot_len;
    const uint8_t* payload = p->payload;
    for (uint i = 0; i < payload_size; i++) {
        const uint8_t byte = payload[i];
        switch (telnet_data->state) {
            case NO_COMMAND:
                // An ordinary character received in telnet mode
                if (byte == 0xff) {
                    telnet_data->state = IAC_COMMAND;
                } else {
                    putchar(byte);
                }
                break;
            case IAC_COMMAND:
                switch (byte) {
                    case 0xf0: // Subnegotiation end
                    case 0xf1: // NOP
                    case 0xf2: // Data mark
                    case 0xf3: // Break
                    case 0xf4: // Interrupt process
                    case 0xf5: // Abort output
                    case 0xf6: // Are you there?
                    case 0xf7: // Erase character
                    case 0xf8: // Erase line
                    case 0xf9: // Go ahead
                        telnet_data->state = NO_COMMAND;
                        break;
                    case 0xfa: // Subnegotiation begin
                        telnet_data->state = SUBOPTION;
                        break;
                    case 0xfb: // WILL
                        telnet_data->state = WILL_COMMAND;
                        break;
                    case 0xfc: // WON'T
                        telnet_data->state = WONT_COMMAND;
                        break;
                    case 0xfd: // DO
                        telnet_data->state = DO_COMMAND;
                        break;
                    case 0xfe: // DON'T
                        telnet_data->state = DONT_COMMAND;
                        break;
                    case 0xff: // IAC (escape character)
                        putchar(byte);
                        telnet_data->state = NO_COMMAND;
                        break;
                    default:
                        printf("\nUnknown command %02x\n", byte);
                        telnet_data->state = NO_COMMAND;
                        break;
                }
                break;
            case WILL_COMMAND:
            case WONT_COMMAND:
                // A proper telnet client would use these commands
                // to learn about what the server can/can't do. But this is just a demo!
                // We follow the approach used by the netcat program and just say no.
                send_buffer_add_byte(telnet_data, 0xff); // IAC
                send_buffer_add_byte(telnet_data, 0xfe); // DON'T
                send_buffer_add_byte(telnet_data, byte); // whatever was asked for
                telnet_data->state = NO_COMMAND;
                break;
            case DO_COMMAND:
            case DONT_COMMAND:
                // As above
                send_buffer_add_byte(telnet_data, 0xff); // IAC
                send_buffer_add_byte(telnet_data, 0xfc); // WON'T
                send_buffer_add_byte(telnet_data, byte); // whatever was asked for
                telnet_data->state = NO_COMMAND;
                break;
            case SUBOPTION:
                // Ignore suboption
                if (byte == 0xff) {
                    telnet_data->state = IAC_COMMAND;
                }
                break;
        }
    }
    fflush(stdout);

    // mark data as received, free pbuf
    tcp_recved(tcp_pcb, p->tot_len);
    pbuf_free(p);
    return ERR_OK;
}


void activity_telnet_test() {
    ui_clear();
    printf("Please enter a host name or IP address:\n");
    if (strlen(g_telnet_address) == 0) {
        strcpy(g_telnet_address, "nethack.alt.org");
    }
    if ((!ui_text_entry(g_telnet_address, sizeof(g_telnet_address))) || (strlen(g_telnet_address) == 0)) {
        return; // cancel
    }

    ip_addr_t addr;
    if (!dns_lookup(g_telnet_address, &addr)) {
        printf("Unable to resolve address\n");
        ui_wait_for_the_user();
        return;
    }

    printf("Please enter the TCP port number:\n");
    if (strlen(g_telnet_port) == 0) {
        strcpy(g_telnet_port, "23");
    }
    if ((!ui_text_entry(g_telnet_port, sizeof(g_telnet_port))) || (strlen(g_telnet_port) == 0)) {
        return; // cancel
    }

    char* end = NULL;
    long port = strtol(g_telnet_port, &end, 10);
    if ((port <= 0) || (port > 0xffff) || (end[0] != '\0')) {
        printf("Invalid port number\n");
        ui_wait_for_the_user();
        return;
    }

    printf("Connecting...\n");

    telnet_data_t telnet_data;
    memset(&telnet_data, 0, sizeof(telnet_data));
    telnet_data.state = NO_COMMAND;

    cyw43_arch_lwip_begin();
    telnet_data.tcp_pcb = tcp_new_ip_type(IP_GET_TYPE(&addr));
    err_t err = ERR_MEM;
    if (telnet_data.tcp_pcb) {
        tcp_arg(telnet_data.tcp_pcb, &telnet_data);
        tcp_sent(telnet_data.tcp_pcb, telnet_client_sent);
        tcp_recv(telnet_data.tcp_pcb, telnet_client_recv);
        tcp_err(telnet_data.tcp_pcb, telnet_client_err);
        err = tcp_connect(telnet_data.tcp_pcb,
                &addr, (uint16_t) port, telnet_client_connected);
    }
    cyw43_arch_lwip_end();

    if (err != ERR_OK) {
        printf("Connection failed, setup error = %d\n", err);
        ui_wait_for_the_user();
        return;
    }
    while (!telnet_data.finish) {
        const int ch = getchar_timeout_us(1000);
        if (ch == CONTROL_ESC) {
            // force disconnect
            break;
        }
        cyw43_arch_lwip_begin();
        if (ch >= 0) {
            // new character received from the user
            send_buffer_add_byte(&telnet_data, (uint8_t) ch);
        }
        if ((ch < 0) || (send_buffer_get_count(&telnet_data) >= FORCE_SEND_THRESHOLD)) {
            // send data if possible
            telnet_client_try_to_send_more_bytes(&telnet_data);
        }
        cyw43_arch_lwip_end();
    }
    telnet_client_close(telnet_data.tcp_pcb);
    printf("\n");
    ui_wait_for_the_user();
}
