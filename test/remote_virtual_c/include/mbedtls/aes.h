#ifndef MBEDTLS_AES_H
#define MBEDTLS_AES_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#include <stdint.h>
#include <stddef.h>

#define _AES_KEY_SIZE       32
#define _AES_BLOCK_SIZE     16

#define MBEDTLS_AES_ENCRYPT 90
#define MBEDTLS_AES_DECRYPT 91

typedef struct mbedtls_aes_context {
    uint8_t key[_AES_KEY_SIZE];
    int direction;
} mbedtls_aes_context;


void mbedtls_aes_init(mbedtls_aes_context* mctx);
int mbedtls_aes_setkey_enc(mbedtls_aes_context* mctx,
                const uint8_t* raw_key, uint32_t key_size);
int mbedtls_aes_setkey_dec(mbedtls_aes_context* mctx,
                const uint8_t* raw_key, uint32_t key_size);
int mbedtls_aes_crypt_cbc(mbedtls_aes_context* mctx,
                int mode, size_t length,
                uint8_t iv[_AES_BLOCK_SIZE],
                const uint8_t* src,
                uint8_t* dest);

#endif

