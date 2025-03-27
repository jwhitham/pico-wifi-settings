#ifndef LWIP_TCP_H
#define LWIP_TCP_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#include <stdint.h>
#include <stdbool.h>

typedef uint8_t err_t;
typedef uint16_t u16_t;
typedef uint8_t u8_t;
typedef struct ip_addr_t{
    uint32_t addr;
} ip_addr_t;

#define ERR_OK      0
#define ERR_ABRT    51
#define ERR_ARG     52
#define TCP_WRITE_FLAG_COPY 53
#define IPADDR_TYPE_ANY 54
#define ERR_MEM     55

struct tcp_pcb;

struct pbuf {
    uint8_t* payload;
    uint16_t len;
};

typedef err_t (*tcp_accept_fn)(void *arg, struct tcp_pcb *newpcb, err_t err);
typedef err_t (*tcp_recv_fn)(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err);
typedef err_t (*tcp_sent_fn)(void *arg, struct tcp_pcb *tpcb, u16_t len);
typedef void (*tcp_err_fn)(void *arg, err_t err);



uint16_t tcp_sndbuf(struct tcp_pcb *pcb);
void tcp_arg(struct tcp_pcb *pcb, void *arg);
void tcp_recv(struct tcp_pcb *pcb, tcp_recv_fn recv);
void tcp_sent(struct tcp_pcb *pcb, tcp_sent_fn sent);
void tcp_err(struct tcp_pcb *pcb, tcp_err_fn err);
void tcp_accept(struct tcp_pcb *pcb, tcp_accept_fn accept);
void tcp_abort(struct tcp_pcb *pcb);
err_t tcp_close(struct tcp_pcb *pcb);
err_t tcp_write(struct tcp_pcb *pcb, const void *dataptr, u16_t len, u8_t apiflags);
struct tcp_pcb * tcp_listen_with_backlog(struct tcp_pcb *pcb, u8_t backlog);
struct tcp_pcb * tcp_new_ip_type(u8_t type);
err_t tcp_bind(struct tcp_pcb *pcb, const ip_addr_t *ipaddr, u16_t port);
bool fake_lwip_loop();

#endif
