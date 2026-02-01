#ifndef COMMON_H
#define COMMON_H

#include <stdint.h>

typedef uint8_t err_t;
typedef uint16_t u16_t;
typedef uint8_t u8_t;
typedef struct ip_addr_t{
    uint32_t addr;
} ip_addr_t;


#define ERR_OK              0

// each magical number should be unique with no relation to whatever LWIP uses:
#define ERR_ABRT            51
#define ERR_ARG             52
#define TCP_WRITE_FLAG_COPY 53
#define IPADDR_TYPE_ANY     54
#define ERR_MEM             55
#define ERR_VAL             56
#define PBUF_TRANSPORT      57
#define PBUF_RAM            58
bool fake_lwip_loop();

#endif
