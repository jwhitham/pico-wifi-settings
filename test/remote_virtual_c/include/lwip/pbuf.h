#ifndef PBUF_H
#define PBUF_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#include <stdint.h>

#include "lwip/common.h"

typedef int pbuf_layer;
typedef int pbuf_type;

struct pbuf {
    uint8_t* payload;
    uint16_t len;
};

struct pbuf* pbuf_alloc (pbuf_layer layer, u16_t length, pbuf_type type);
void pbuf_free(struct pbuf *p);

#endif
