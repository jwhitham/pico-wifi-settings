#ifndef MBEDTLS_SHA256_H
#define MBEDTLS_SHA256_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#define _SHA256_BLOCK_SIZE  32

#include <stdbool.h>
#include <stddef.h>

typedef struct mbedtls_sha256_context {
    bool active;
    void* opaque_ctx;
    void* opaque_hash;
} mbedtls_sha256_context;

void mbedtls_sha256_init(mbedtls_sha256_context *ctx);
void mbedtls_sha256_free(mbedtls_sha256_context *ctx);
int mbedtls_sha256_starts(mbedtls_sha256_context *ctx, int is224);
int mbedtls_sha256_update(mbedtls_sha256_context *ctx,
                              const unsigned char *input,
                              size_t ilen);
int mbedtls_sha256_finish(mbedtls_sha256_context *ctx,
                              unsigned char output[_SHA256_BLOCK_SIZE]);

#endif

