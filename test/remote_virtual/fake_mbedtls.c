/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This is a minimal mbedtls-like API which uses OpenSSL AES/SHA functions.
 *
 */

#include "remote_virtual.h"
#include "mbedtls/aes.h"
#include "mbedtls/sha256.h"
#include "pico/rand.h"

#include <openssl/conf.h>
#include <openssl/evp.h>
#include <openssl/err.h>
#include <openssl/rand.h>
#include <string.h>

void mbedtls_aes_init(mbedtls_aes_context* mctx) {
    ASSERT(mctx);
}

int mbedtls_aes_setkey_enc(mbedtls_aes_context* mctx,
                const uint8_t* raw_key, uint32_t key_size) {
    ASSERT(mctx);
    ASSERT(key_size == (_AES_KEY_SIZE * 8));
    memcpy(mctx->key, raw_key, _AES_KEY_SIZE);
    mctx->direction = MBEDTLS_AES_ENCRYPT;
    return 0;
}

int mbedtls_aes_setkey_dec(mbedtls_aes_context* mctx,
                const uint8_t* raw_key, uint32_t key_size) {
    mbedtls_aes_setkey_enc(mctx, raw_key, key_size);
    mctx->direction = MBEDTLS_AES_DECRYPT;
    return 0;
}

int mbedtls_aes_crypt_cbc(mbedtls_aes_context* mctx,
                int mode, size_t length,
                uint8_t iv[_AES_BLOCK_SIZE],
                const uint8_t* src,
                uint8_t* dest) {
    ASSERT(mctx);
    ASSERT((mode == MBEDTLS_AES_ENCRYPT) || (mode == MBEDTLS_AES_DECRYPT));
    ASSERT(mode == mctx->direction);
    ASSERT(length == _AES_BLOCK_SIZE);
    
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    ASSERT(ctx);

    EVP_CIPHER *cipher = EVP_CIPHER_fetch(NULL, "AES-256-CBC", NULL);
    ASSERT(cipher);

    if (mode == MBEDTLS_AES_ENCRYPT) {
        int rc = EVP_EncryptInit_ex(ctx, cipher, NULL, mctx->key, iv);
        ASSERT(rc == 1);

        EVP_CIPHER_CTX_set_padding(ctx, 0);

        int len_out = 0;
        rc = EVP_EncryptUpdate(ctx, dest, &len_out, src, _AES_BLOCK_SIZE);
        ASSERT(rc == 1);
        ASSERT(len_out == _AES_BLOCK_SIZE);
        memcpy(iv, dest, _AES_BLOCK_SIZE);

        uint8_t ignore[1];
        rc = EVP_EncryptFinal_ex(ctx, ignore, &len_out);
        ASSERT(rc == 1);
        ASSERT(len_out == 0);
    } else {

        int rc = EVP_DecryptInit_ex(ctx, cipher, NULL, mctx->key, iv);
        ASSERT(rc == 1);

        EVP_CIPHER_CTX_set_padding(ctx, 0);

        memcpy(iv, src, _AES_BLOCK_SIZE);
        int len_out = 0;
        rc = EVP_DecryptUpdate(ctx, dest, &len_out, src, _AES_BLOCK_SIZE);
        ASSERT(rc == 1);
        ASSERT(len_out == _AES_BLOCK_SIZE);

        uint8_t ignore[1];
        rc = EVP_DecryptFinal_ex(ctx, ignore, &len_out);
        ASSERT(rc == 1);
        ASSERT(len_out == 0);
    }

    EVP_CIPHER_free(cipher);
    EVP_CIPHER_CTX_free(ctx);
    return 0;
}

void mbedtls_sha256_init(mbedtls_sha256_context *mctx) {
    ASSERT(mctx);

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    ASSERT(ctx);

    EVP_MD* hash = EVP_MD_fetch(NULL, "SHA-256", NULL);
    ASSERT(hash);
    ASSERT(EVP_MD_size(hash) == _SHA256_BLOCK_SIZE);

    mctx->opaque_ctx = ctx;
    mctx->opaque_hash = hash;
    mctx->active = false;
}

void mbedtls_sha256_free(mbedtls_sha256_context *mctx) {
    ASSERT(mctx);
    ASSERT(!mctx->active);

    EVP_MD_CTX* ctx = (EVP_MD_CTX*) mctx->opaque_ctx;
    ASSERT(ctx);
    EVP_MD* hash = (EVP_MD*) mctx->opaque_hash;
    ASSERT(hash);

    EVP_MD_free(hash);
	EVP_MD_CTX_free(ctx);

    mctx->opaque_ctx = NULL;
    mctx->opaque_hash = NULL;
}

int mbedtls_sha256_starts_ret(mbedtls_sha256_context *mctx, int is224) {
    ASSERT(mctx);
    ASSERT(!is224);

    EVP_MD_CTX* ctx = (EVP_MD_CTX*) mctx->opaque_ctx;
    ASSERT(ctx);
    EVP_MD* hash = (EVP_MD*) mctx->opaque_hash;
    ASSERT(hash);

    ASSERT(!mctx->active);
    mctx->active = true;

    int rc = EVP_DigestInit_ex(ctx, hash, NULL);
    ASSERT(rc == 1);
    return 0;
}

int mbedtls_sha256_update_ret(mbedtls_sha256_context *mctx,
                              const unsigned char *input,
                              size_t ilen) {
    ASSERT(mctx);
    ASSERT(mctx->active);

    EVP_MD_CTX* ctx = (EVP_MD_CTX*) mctx->opaque_ctx;
    ASSERT(ctx);
	int rc = EVP_DigestUpdate(ctx, input, ilen);
    ASSERT(rc == 1);
    return 0;
}

int mbedtls_sha256_finish_ret(mbedtls_sha256_context *mctx,
                              unsigned char output[_SHA256_BLOCK_SIZE]) {
    ASSERT(mctx);
    ASSERT(mctx->active);

    EVP_MD_CTX* ctx = (EVP_MD_CTX*) mctx->opaque_ctx;
    ASSERT(ctx);

    unsigned len = 0;
	int rc = EVP_DigestFinal_ex(ctx, output, &len);
    ASSERT(rc == 1);
    ASSERT(len == _SHA256_BLOCK_SIZE);
    mctx->active = false;
    return 0;
}

void get_rand_128(rng_128_t *rand128) {
    int rc = RAND_bytes((unsigned char*) rand128, sizeof(rng_128_t));
    ASSERT(rc == 1);
}
