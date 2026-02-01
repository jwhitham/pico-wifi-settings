#ifndef LWIP_UDP_H
#define LWIP_UDP_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#include "lwip/common.h"
#include "lwip/pbuf.h"

struct udp_pcb;

err_t udp_sendto(struct udp_pcb* pcb, struct pbuf* p, const ip_addr_t* dst_ip, u16_t dst_port);
struct udp_pcb* udp_new_ip_type(u8_t type);
void udp_recv(struct udp_pcb* pcb, udp_recv_fn recv, void * recv_arg);
err_t udp_bind(struct udp_pcb* pcb, const ip_addr_t* ipaddr, u16_t port);


#endif
