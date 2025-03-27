/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Remote update service for wifi-settings.
 */


#include "wifi_settings.h"
#include "wifi_settings/wifi_settings_remote.h"
#include "wifi_settings/wifi_settings_remote_handlers.h"
#include "wifi_settings/wifi_settings_remote_memory_access_handlers.h"
#include "wifi_settings/wifi_settings_flash_storage.h"

#include "pico/rand.h"
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "mbedtls/sha256.h"
#include "mbedtls/aes.h"
#include "lwip/tcp.h"
#include "lwip/udp.h"

#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdbool.h>
#include <sys/types.h>
#include <inttypes.h>
#include <stdlib.h>

#ifndef MBEDTLS_AES_C
#error "MBEDTLS_AES_C must be enabled"
#endif
#ifndef MBEDTLS_CIPHER_MODE_CBC
#error "MBEDTLS_CIPHER_MODE_CBC must be enabled"
#endif
#ifndef LWIP_CALLBACK_API
#error "LWIP_CALLBACK_API must be enabled"
#endif
#ifndef ENABLE_REMOTE_UPDATE
#error "ENABLE_REMOTE_UPDATE must be enabled"
#endif
#ifndef WIFI_SETTINGS_VERSION_STRING
#error "WIFI_SETTINGS_VERSION_STRING must be set"
#endif


#define PORT_NUMBER                 1404
#define RESPONDER_REQUEST_MAGIC     "PWS?"
#define RESPONDER_REPLY_MAGIC       "PWS:"
#define APPEND_CODE_SIZE            2
#define CHALLENGE_SIZE              15      // max is AES_BLOCK_SIZE - 1
#define AUTHENTICATION_SIZE         15      // max is AES_BLOCK_SIZE - 1
#define HMAC_DIGEST_SIZE            32      // 256 bits (SHA-256)
#define HMAC_BLOCK_SIZE             64
#define AES_BLOCK_SIZE              16
#define AES_KEY_SIZE                32      // 256 bits (AES-256)
#define DATA_HASH_SIZE              7
#define PROTOCOL_VERSION            1

typedef enum msg_type_t {
    ID_GREETING =           70, // s->c
    ID_REQUEST =            71, // s<-c
    ID_CHALLENGE =          72, // s->c
    ID_AUTHENTICATION =     73, // s<-c
    ID_RESPONSE =           74, // s->c
    ID_ACKNOWLEDGE =        75, // s<-c
    ID_OK =                 76, // s->c
    ID_AUTH_ERROR =         77, // both
    ID_VERSION_ERROR =      78, // both
    ID_BAD_MSG_ERROR =      79, // both
    ID_BAD_PARAM_ERROR =    80, // s->c
    ID_BAD_HANDLER_ERROR =  81, // s->c
    ID_NO_SECRET_ERROR =    82, // s->c
    ID_CORRUPT_ERROR =      83, // s->c
    ID_UNKNOWN_ERROR =      84, // s->c
    // Message handlers (callbacks)
    // First 8 are reserved for wifi_settings_remote
    ID_PICO_INFO_HANDLER =      120,
    ID_UPDATE_HANDLER =         121,
    ID_READ_HANDLER =           122,
    ID_RESERVED_3 =             123,
    ID_UPDATE_REBOOT_HANDLER =  124,
    ID_WRITE_FLASH_HANDLER =    125,
    ID_RESERVED_6 =             126,
    ID_OTA_FIRMWARE_UPDATE_HANDLER = 127,
    // The rest are available for reuse
    ID_USER_HANDLER_0 =         ID_FIRST_USER_HANDLER,
    ID_USER_HANDLER_N =         ID_LAST_USER_HANDLER,
} msg_type_t;

#define ID_FIRST_HANDLER    ID_PICO_INFO_HANDLER
#define NUM_HANDLERS        (ID_LAST_USER_HANDLER + 1 - ID_FIRST_HANDLER)

typedef enum receive_state_t {
    // Authentication states (unencrypted)
    SEND_GREETING = 1,
    EXPECT_REQUEST,
    SEND_CHALLENGE,
    EXPECT_AUTHENTICATION,
    SEND_AUTHENTICATION,
    EXPECT_ACKNOWLEDGE,
    SEND_BAD_MSG_ERROR,
    SEND_AUTH_ERROR,
    SEND_NO_SECRET_ERROR,
    // Encrypted communication states
    EXPECT_ENC_REQUEST_HEADER,
    EXPECT_ENC_REQUEST_PAYLOAD,
    SEND_ENC_REPLY_HEADER,
    SEND_ENC_REPLY_PAYLOAD,
    SEND_CORRUPT_ERROR,
    SEND_BAD_PARAM_ERROR,
    SEND_BAD_HANDLER_ERROR,
    SEND_ENC_REPLY_HEADER_WITH_CALLBACK2,
    // Special state when waiting to finish sending
    EXECUTE_CALLBACK2,
    // Disconnected state
    DISCONNECT,
} receive_state_t;

// The size of this structure should be AES_BLOCK_SIZE
typedef struct enc_message_header_t {
    uint32_t    data_size;
    int32_t     parameter_or_result;
    uint8_t     msg_type;
    uint8_t     data_hash[DATA_HASH_SIZE];
} enc_message_header_t;

typedef struct session_t {
    uint8_t                     data[MAX_DATA_SIZE];
    uint8_t                     client_challenge[CHALLENGE_SIZE];
    uint8_t                     server_challenge[CHALLENGE_SIZE];
    uint8_t                     output_block[AES_BLOCK_SIZE];
    bool                        output_block_ready;
    uint8_t                     input_block[AES_BLOCK_SIZE];
    uint8_t                     input_block_offset;
    uint8_t                     decrypt_iv[AES_BLOCK_SIZE];
    uint8_t                     encrypt_iv[AES_BLOCK_SIZE];
    mbedtls_aes_context         decrypt;
    mbedtls_aes_context         encrypt;
    enc_message_header_t        reply_header;
    enc_message_header_t        request_header;
    receive_state_t             state;
    uint32_t                    data_index;
} session_t;

typedef struct handler_callback_arg_t {
    handler_callback1_t callback1;
    handler_callback2_t callback2;
    void* arg;
} handler_callback_arg_t;

typedef struct responder_packet_t {
    uint8_t magic[4];
    uint8_t board_id_hex[(BOARD_ID_SIZE * 2) + 1];
} responder_packet_t;


static handler_callback_arg_t g_handler_table[NUM_HANDLERS];
static struct tcp_pcb* g_remote_service_pcb = NULL;
static struct udp_pcb* g_responder_service_pcb = NULL;
static uint8_t g_secret_hashed[HMAC_DIGEST_SIZE];
static bool g_secret_valid;


static void generate_authentication(
        session_t* session,
        const char* append_code,
        uint8_t* output,
        const uint output_size) {
    // HMAC SHA-256 -> key is the hashed secret
    uint8_t k_pad[HMAC_BLOCK_SIZE];
    uint8_t digest_data[HMAC_DIGEST_SIZE];
    uint i;

    for (i = 0; i < HMAC_DIGEST_SIZE; i++) {
        k_pad[i] = g_secret_hashed[i] ^ 0x36;
    }
    for (; i < HMAC_BLOCK_SIZE; i++) {
        k_pad[i] = 0x36;
    }
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    if ((0 != mbedtls_sha256_starts_ret(&ctx, 0))
    || (0 != mbedtls_sha256_update_ret(&ctx, k_pad, HMAC_BLOCK_SIZE))
    || (0 != mbedtls_sha256_update_ret(&ctx, session->client_challenge, CHALLENGE_SIZE))
    || (0 != mbedtls_sha256_update_ret(&ctx, session->server_challenge, CHALLENGE_SIZE))
    || (0 != mbedtls_sha256_update_ret(&ctx, (const uint8_t*) append_code, APPEND_CODE_SIZE))
    || (0 != mbedtls_sha256_finish_ret(&ctx, digest_data))) {
        panic("generate_authentication sha256 (1) failed");
    }
    for (i = 0; i < HMAC_BLOCK_SIZE; i++) {
        k_pad[i] ^= 0x5c ^ 0x36;
    }
    if ((0 != mbedtls_sha256_starts_ret(&ctx, 0))
    || (0 != mbedtls_sha256_update_ret(&ctx, k_pad, HMAC_BLOCK_SIZE))
    || (0 != mbedtls_sha256_update_ret(&ctx, digest_data, HMAC_DIGEST_SIZE))
    || (0 != mbedtls_sha256_finish_ret(&ctx, digest_data))) {
        panic("generate_authentication sha256 (2) failed");
    }
    mbedtls_sha256_free(&ctx);
    memcpy(output, digest_data, output_size);
}

static void generate_keys(session_t* session) {

    uint8_t raw_key[AES_KEY_SIZE];

    generate_authentication(session, "SK", raw_key, AES_KEY_SIZE);
    memset(session->encrypt_iv, 0, AES_BLOCK_SIZE);
    mbedtls_aes_init(&session->encrypt);
    if (0 != mbedtls_aes_setkey_enc(&session->encrypt,
                raw_key, AES_KEY_SIZE * 8)) {
        panic("generate_keys aes (1) failed");
    }

    generate_authentication(session, "CK", raw_key, AES_KEY_SIZE);
    memset(session->decrypt_iv, 0, AES_BLOCK_SIZE);
    mbedtls_aes_init(&session->decrypt);
    if (0 != mbedtls_aes_setkey_dec(&session->decrypt,
                raw_key, AES_KEY_SIZE * 8)) {
        panic("generate_keys aes (2) failed");
    }

    memset(raw_key, 0, sizeof(AES_KEY_SIZE));
}

static void encrypt_block(
        session_t* session,
        const uint8_t* src) {
    uint8_t* dest = session->output_block;

    if (0 != mbedtls_aes_crypt_cbc(&session->encrypt, MBEDTLS_AES_ENCRYPT,
                          AES_BLOCK_SIZE, session->encrypt_iv,
                          src, dest)) {
        panic("encrypt_block failed");
    }
}

static void decrypt_block(
        session_t* session,
        uint8_t* dest) {
    const uint8_t* src = session->input_block;

    if (0 != mbedtls_aes_crypt_cbc(&session->decrypt, MBEDTLS_AES_DECRYPT,
                          AES_BLOCK_SIZE, session->decrypt_iv,
                          src, dest)) {
        panic("decrypt_block failed");
    }
}

static void generate_enc_data_hash(
        session_t* session,
        enc_message_header_t* header,
        uint8_t* data_hash) {

    // Generate data hash for the reply header and payload (if any)
    uint8_t full_data_hash[HMAC_DIGEST_SIZE];
    mbedtls_sha256_context ctx;

    mbedtls_sha256_init(&ctx);
    if ((0 != mbedtls_sha256_starts_ret(&ctx, 0))
    || (0 != mbedtls_sha256_update_ret(&ctx, (uint8_t*) header,
                    AES_BLOCK_SIZE - DATA_HASH_SIZE))
    || (0 != mbedtls_sha256_update_ret(&ctx, session->data,
                    header->data_size))
    || (0 != mbedtls_sha256_finish_ret(&ctx, full_data_hash))) {
        panic("generate_enc_data_hash sha256 failed");
    }
    mbedtls_sha256_free(&ctx);
    memcpy(data_hash, full_data_hash, DATA_HASH_SIZE);
}

static void generate_enc_header_for_error(
        session_t* session,
        msg_type_t msg_type) {

    // Generate an encrypted reply header containing the error msg_type
    memset(&session->reply_header, 0, AES_BLOCK_SIZE);
    session->reply_header.msg_type = msg_type;

    // Add data hash
    generate_enc_data_hash(session, &session->reply_header, session->reply_header.data_hash);

    // Encrypt
    encrypt_block(session, (const uint8_t*) &session->reply_header);
    session->state = DISCONNECT;
}

static void generate_clear_header_for_error(
        session_t* session,
        msg_type_t msg_type) {

    // Generate an unencrypted reply header containing the error msg_type
    uint8_t* block = session->output_block;
    memset(block, 0, AES_BLOCK_SIZE);
    block[0] = msg_type;
    session->state = DISCONNECT;
}

static bool generate_output_block(session_t* session) {
    uint8_t* block = session->output_block;
    switch (session->state) {
        case SEND_GREETING:
            // First message, server to client. Say hello.
            memcpy(block, &session->data[session->data_index], AES_BLOCK_SIZE);
            session->data_index += AES_BLOCK_SIZE;
            if (session->data_index >= session->reply_header.data_size) {
                session->state = EXPECT_REQUEST;
            }
            return true;
        case EXPECT_REQUEST:
            // Second message, client to server. Client sends the client challenge.
            return false;
        case SEND_CHALLENGE:
            // Third message, server to client. Server sends the server challenge.
            {
                rng_128_t rng;
                get_rand_128(&rng);
                block[0] = ID_CHALLENGE;
                memcpy(session->server_challenge, &rng, CHALLENGE_SIZE);
                memcpy(&block[1], &rng, CHALLENGE_SIZE);
                session->state = EXPECT_AUTHENTICATION;
            }
            return true;
        case EXPECT_AUTHENTICATION:
            // Fourth message, client to server. Client sends the client authentication.
            return false;
        case SEND_AUTHENTICATION:
            // Fifth message, server to client. Server sends the server authentication.
            block[0] = ID_RESPONSE;
            generate_authentication(session, "SA", &block[1], AUTHENTICATION_SIZE);
            session->state = EXPECT_ACKNOWLEDGE;
            return true;
        case EXPECT_ACKNOWLEDGE:
            // Sixth message, client to server. Client indicates authentication is complete.
            return false;
        case SEND_BAD_MSG_ERROR:
            // Report bad message error to the client.
            generate_clear_header_for_error(session, ID_BAD_MSG_ERROR);
            return true;
        case SEND_AUTH_ERROR:
            // Report authentication error to the client.
            generate_clear_header_for_error(session, ID_AUTH_ERROR);
            return true;
        case SEND_NO_SECRET_ERROR:
            // Report 'no secret' error to the client.
            generate_clear_header_for_error(session, ID_NO_SECRET_ERROR);
            return true;
        case SEND_CORRUPT_ERROR:
            // Encrypted stage. Report corrupt encrypted data error to the client.
            generate_enc_header_for_error(session, ID_CORRUPT_ERROR);
            return true;
        case SEND_BAD_PARAM_ERROR:
            // Encrypted stage. Report bad parameter error to the client.
            generate_enc_header_for_error(session, ID_BAD_PARAM_ERROR);
            return true;
        case SEND_BAD_HANDLER_ERROR:
            // Encrypted stage. Report bad handler error to the client.
            generate_enc_header_for_error(session, ID_BAD_HANDLER_ERROR);
            return true;
        case EXPECT_ENC_REQUEST_HEADER:
            // Encrypted stage. Awaiting request from the client.
            return false;
        case EXPECT_ENC_REQUEST_PAYLOAD:
            // Encrypted stage. Awaiting payload from the client.
            return false;
        case SEND_ENC_REPLY_HEADER:
            // Encrypted stage. Send reply header to the client.
            encrypt_block(session, (const uint8_t*) &session->reply_header);
            if (session->reply_header.data_size == 0) {
                // Header only - no payload
                session->state = EXPECT_ENC_REQUEST_HEADER;
            } else {
                session->state = SEND_ENC_REPLY_PAYLOAD;
            }
            return true;
        case SEND_ENC_REPLY_PAYLOAD:
            // Encrypted stage. Send payload data to the client.
            encrypt_block(session, &session->data[session->data_index]);
            session->data_index += AES_BLOCK_SIZE;
            if (session->data_index >= session->reply_header.data_size) {
                // Finished
                session->state = EXPECT_ENC_REQUEST_HEADER;
            }
            return true;
        case SEND_ENC_REPLY_HEADER_WITH_CALLBACK2:
            // Encrypted stage. Send reply header to the client (callback2 pending).
            encrypt_block(session, (const uint8_t*) &session->reply_header);
            session->state = EXECUTE_CALLBACK2;
            return true;
        case EXECUTE_CALLBACK2:
            // Execute callback2 handler when header has been sent (nothing should be sent).
            return false;
        case DISCONNECT:
            return false;
    }
    return false;
}

static void handle_enc_request_end(session_t* session) {
    // Check data hash is correct
    uint8_t expect_hash[DATA_HASH_SIZE];
    generate_enc_data_hash(session, &session->request_header, expect_hash);
    if (memcmp(expect_hash, session->request_header.data_hash, DATA_HASH_SIZE) != 0) {
        session->state = SEND_CORRUPT_ERROR;
        return;
    }

    memset(&session->reply_header, 0, AES_BLOCK_SIZE);
    session->reply_header.msg_type = ID_OK;

    // Process the request, getting new data, data_size, parameter
    uint8_t handler_id = session->request_header.msg_type - ID_FIRST_HANDLER;

    // Check handler is valid (this was already checked, but g_handler_table may have changed)
    if ((handler_id >= NUM_HANDLERS)
    || !(g_handler_table[(uint) handler_id].callback1
            || g_handler_table[(uint) handler_id].callback2)) {
        session->state = SEND_BAD_HANDLER_ERROR;
        return;
    }

    uint32_t reply_data_size = session->request_header.data_size;
    int32_t result = session->request_header.parameter_or_result;

    if (g_handler_table[(uint) handler_id].callback1) {
        // call first handler
        reply_data_size = MAX_DATA_SIZE;
        result = g_handler_table[(uint) handler_id].callback1(
                session->request_header.msg_type,
                session->data,
                session->request_header.data_size,
                session->request_header.parameter_or_result,
                &reply_data_size,
                g_handler_table[(uint) handler_id].arg);
        // The handler should not increase reply_data_size, try to do something useful anyway:
        if (reply_data_size > MAX_DATA_SIZE) {
            reply_data_size = MAX_DATA_SIZE;
        }
    }

    session->data_index = 0;
    session->reply_header.parameter_or_result = result;

    if (g_handler_table[(uint) handler_id].callback2) {
        // prepare to call the second handler; no data will be sent via the network,
        // but it will be available for callback2
        session->reply_header.data_size = 0;
        session->request_header.data_size = reply_data_size;
        session->request_header.parameter_or_result = result;
        session->state = SEND_ENC_REPLY_HEADER_WITH_CALLBACK2;
    } else {
        // no second handler, return data
        session->reply_header.data_size = reply_data_size;
        session->state = SEND_ENC_REPLY_HEADER;
    }
    generate_enc_data_hash(session, &session->reply_header, session->reply_header.data_hash);
}

static void handle_enc_request_start(session_t* session) {
    // Decrypt 
    decrypt_block(session, (uint8_t*) &session->request_header);

    // Check handler ID is within the allowed range
    uint8_t handler_id = session->request_header.msg_type - ID_FIRST_HANDLER;
    if ((handler_id >= NUM_HANDLERS)
    || !(g_handler_table[(uint) handler_id].callback1
            || g_handler_table[(uint) handler_id].callback2)) {
        session->state = SEND_BAD_HANDLER_ERROR;
        return;
    }
    // Check parameters are valid, start processing the request
    if (session->request_header.data_size > MAX_DATA_SIZE) {
        session->state = SEND_BAD_PARAM_ERROR;
        return;
    }

    // Prepare for receiving the request payload
    session->data_index = 0;
    if (session->request_header.data_size == 0) {
        // There is no payload - go direct to the end
        handle_enc_request_end(session);
    } else {
        // Payload needed
        session->state = EXPECT_ENC_REQUEST_PAYLOAD;
    }
}

static void handle_enc_request_add_data(session_t* session) {
    decrypt_block(session, &session->data[session->data_index]);
    session->data_index += AES_BLOCK_SIZE;
    if (session->data_index >= session->request_header.data_size) {
        // No more blocks
        handle_enc_request_end(session);
    }
}

static bool handle_input_block(session_t* session) {
    const uint8_t* block = session->input_block;
    switch (session->state) {
        case SEND_GREETING:
            // First message, server to client. Say hello.
            return false;
        case EXPECT_REQUEST:
            // Second message, client to server. Client sends the client challenge.
            if (block[0] != ID_REQUEST) {
                session->state = SEND_BAD_MSG_ERROR;
            } else if (!g_secret_valid) {
                session->state = SEND_NO_SECRET_ERROR;
            } else {
                memcpy(session->client_challenge, &block[1], CHALLENGE_SIZE);
                session->state = SEND_CHALLENGE;
            }
            return true;
        case SEND_CHALLENGE:
            // Third message, server to client. Server sends the server challenge.
            return false;
        case EXPECT_AUTHENTICATION:
            // Fourth message, client to server. Client sends the client authentication.
            if (block[0] != ID_AUTHENTICATION) {
                session->state = SEND_BAD_MSG_ERROR;
            } else {
                uint8_t check_authentication[AUTHENTICATION_SIZE];
                generate_authentication(session, "CA", check_authentication, AUTHENTICATION_SIZE);
                if (memcmp(check_authentication, &block[1], AUTHENTICATION_SIZE) != 0) {
                    session->state = SEND_AUTH_ERROR;
                } else {
                    session->state = SEND_AUTHENTICATION;
                }
            }
            return true;
        case SEND_AUTHENTICATION:
            // Fifth message, server to client. Server sends the server authentication.
            return false;
        case EXPECT_ACKNOWLEDGE:
            // Sixth message, client to server. Client indicates authentication is complete.
            if (block[0] != ID_ACKNOWLEDGE) {
                session->state = SEND_BAD_MSG_ERROR;
            } else {
                session->state = EXPECT_ENC_REQUEST_HEADER;
                // Session keys can be generated now
                generate_keys(session);
            }
            return true;
        case SEND_BAD_MSG_ERROR:
            // Report bad message error to the client.
            return false;
        case SEND_BAD_PARAM_ERROR:
            // Report bad request parameter error to the client.
            return false;
        case SEND_BAD_HANDLER_ERROR:
            // Report bad handler error to the client.
            return false;
        case SEND_AUTH_ERROR:
            // Report authentication error to the client.
            return false;
        case SEND_NO_SECRET_ERROR:
            // Report "no secret" error to the client.
            return false;
        case SEND_CORRUPT_ERROR:
            // Report corrupt block error to the client.
            return false;
        case EXPECT_ENC_REQUEST_HEADER:
            // Encrypted stage. Awaiting request from the client.
            handle_enc_request_start(session);
            return true;
        case EXECUTE_CALLBACK2:
            // Execute callback2 handler when header has been sent (nothing should be received).
            return false;
        case EXPECT_ENC_REQUEST_PAYLOAD:
            // Encrypted stage. Awaiting payload data from the client.
            handle_enc_request_add_data(session);
            return true;
        case SEND_ENC_REPLY_HEADER:
            // Encrypted stage. Send reply header to the client.
            return false;
        case SEND_ENC_REPLY_PAYLOAD:
            // Encrypted stage. Send payload data to the client.
            return false;
        case SEND_ENC_REPLY_HEADER_WITH_CALLBACK2:
            // Encrypted stage. Send reply header to the client (callback2 handler pending).
            return false;
        case DISCONNECT:
            return false;
    }
    return false;
}

static void server_tcp_close(struct tcp_pcb *client_pcb) {
    // Disable all callbacks
    tcp_arg(client_pcb, NULL);
    tcp_sent(client_pcb, NULL);
    tcp_recv(client_pcb, NULL);
    tcp_err(client_pcb, NULL);
    // close
    tcp_close(client_pcb);
}

static void server_err(void *arg, err_t unused) {
    // Called if there is a TCP error with the connection or from the remote side.
    // This callback:
    // * must free the arg pointer (if not NULL)
    // * should ignore the err parameter
    // * might be called with arg == NULL
    struct session_t* session = (struct session_t*) arg;
    free(session);
}

static void send_while_able(struct session_t* session, struct tcp_pcb* client_pcb) {
    while (true) {
        // check if an output block is waiting to be sent
        if (!session->output_block_ready) {
            // try to generate an output block
            if (!generate_output_block(session)) {
                // There's nothing to send
                return;
            }
            session->output_block_ready = true;
        }

        // try to send a block
        // Note: can't use tcp_sndbuf to tell if this will succeed, so we have
        // to generate a block beforehand.
        err_t err = tcp_write(client_pcb, session->output_block,
                        AES_BLOCK_SIZE, TCP_WRITE_FLAG_COPY);
        if (err == ERR_OK) {
            // success, block has been sent
            session->output_block_ready = false;
        } else if (err == ERR_MEM) {
            // failure, we should try again later, after some data has been sent
            return;
        } else {
            // some other error - abandon the connection
            session->state = DISCONNECT;
            return;
        }
    }
}

static err_t server_recv(void* arg, struct tcp_pcb* client_pcb, struct pbuf* p, err_t err) {
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
    struct session_t* session = (struct session_t*) arg;

    if ((!p) || (!session)) {
        // connection has been closed by the other side
        free(session);
        server_tcp_close(client_pcb);
        if (p) {
            pbuf_free(p);
        }
        return ERR_OK;
    }

    // copy in to blocks
    uint8_t* payload = (uint8_t*) p->payload;
    uint16_t payload_size = (uint) p->len;
    bool input_buffer_overflow = false;

    for (uint16_t recv_index = 0; recv_index < payload_size; recv_index++) {
        session->input_block[(uint) session->input_block_offset] = payload[(uint) recv_index];
        session->input_block_offset++;
        if (session->input_block_offset >= AES_BLOCK_SIZE) {
            // Process the block
            if (!handle_input_block(session)) {
                // Unable to handle input right now!
                // (There is no buffer space for this.)
                // We will disconnect, possibly after sending an error message
                input_buffer_overflow = true;
                break;
            }
            session->input_block_offset = 0;
        }
    }

    // mark data as received, free pbuf
    tcp_recved(client_pcb, payload_size);
    pbuf_free(p);

    // disconnect before sending anything if requested by handle_input_block
    if (session->state == DISCONNECT) {
        free(session);
        server_tcp_close(client_pcb);
        return ERR_OK;
    }

    // Send data (if any)
    // send_while_able may also enter the DISCONNECT state, but in this case,
    // don't disconnect immediately, wait for server_sent to be called.
    send_while_able(session, client_pcb);

    // If an overflow was detected, disconnect after sending an error message
    if (input_buffer_overflow) {
        session->state = DISCONNECT;
    }
    return ERR_OK;
}

static err_t server_sent(void *arg, struct tcp_pcb *client_pcb, uint16_t unused) {
    // Called when a packet is sent, and so there is more space is the output buffer,
    // possibly allowing more data to be sent.
    //
    // This callback:
    // * may call tcp_close
    // * must return ERR_OK
    // * might be called with arg == NULL (in which case tcp_close is correct behaviour)
    struct session_t* session = (struct session_t*) arg;

    if (!session) {
        server_tcp_close(client_pcb);
        return ERR_OK;
    }

    // Send data?
    send_while_able(session, client_pcb);

    if (session->state == EXECUTE_CALLBACK2) {
        // Data has been sent, execute callback2 if it exists (close first)
        server_tcp_close(client_pcb);

        uint8_t handler_id = session->request_header.msg_type - ID_FIRST_HANDLER;

        if ((handler_id < NUM_HANDLERS)
        && (g_handler_table[(uint) handler_id].callback2)) {
            g_handler_table[(uint) handler_id].callback2(
                session->request_header.msg_type,
                session->data,
                session->request_header.data_size,
                session->request_header.parameter_or_result,
                g_handler_table[(uint) handler_id].arg);
        }
        // Result of executing callback2 cannot be reported
        free(session);
    } else if (session->state == DISCONNECT) {
        free(session);
        server_tcp_close(client_pcb);
    }
    return ERR_OK;
}

static err_t server_accept(void *arg, struct tcp_pcb *client_pcb, err_t err) {
    // Called for a new connection
    //
    // This callback:
    // * should not call tcp_close
    // * must return ERR_OK or ERR_VAL or ERR_MEM
    //   * ERR_MEM if memory couldn't be allocated
    //   * ERR_VAL if (err != ERR_OK) || !pcb
    // * must call tcp_sent, tcp_recv, tcp_err to register callbacks
    // * must call tcp_arg with session data
    if ((err != ERR_OK) || !client_pcb) {
        return ERR_VAL; 
    }

    struct session_t* session = calloc(1, sizeof(struct session_t));
    if (!session) {
        return ERR_MEM;
    }

    tcp_arg(client_pcb, session);
    tcp_sent(client_pcb, server_sent);
    tcp_recv(client_pcb, server_recv);
    tcp_err(client_pcb, server_err);

    // Set up greeting
    int string_size = snprintf((char*) session->data, MAX_DATA_SIZE,
        "xxx\r%s\rpico-wifi-settings version " WIFI_SETTINGS_VERSION_STRING "\r\n",
        wifi_settings_get_board_id_hex());
    // bytes 0 .. 2 are fixed fields in the reply:
    session->data[0] = ID_GREETING;
    session->data[1] = PROTOCOL_VERSION;
    session->data[2] = (uint8_t) ((string_size + AES_BLOCK_SIZE - 1) / AES_BLOCK_SIZE);
    // bytes 4 .. 19 contain the board ID in uppercase hex format
    session->reply_header.data_size = ((uint32_t) session->data[2]) * AES_BLOCK_SIZE;
    // bytes 20 .. <unspecified> contain UTF-8 text that can be printed

    session->state = SEND_GREETING;
    send_while_able(session, client_pcb);
    return ERR_OK;
}

static void responder_recv(
        void* unused,
        struct udp_pcb *pcb,
        struct pbuf *p,
        const ip_addr_t *addr,
        u16_t port) {
  
    // Copy the request into a responder_packet_t
    responder_packet_t mp;
    memset(&mp, 0, sizeof(mp));
    if (p->payload) {
        memcpy(&mp, p->payload, (sizeof(mp) < p->len) ? sizeof(mp) : p->len);
    }
    pbuf_free(p); // No longer required

    // Check magic
    if (memcmp(mp.magic, RESPONDER_REQUEST_MAGIC, sizeof(mp.magic)) != 0) {
        // Invalid request - not magic
        return;
    }
    // Check board ID
    mp.board_id_hex[BOARD_ID_SIZE * 2] = '\0';
    const char* my_board_id_hex = wifi_settings_get_board_id_hex();
    if (strstr(my_board_id_hex, (const char*) mp.board_id_hex) == NULL) {
        // Request is for a different board
        return;
    }
    // Respond to request with complete board id
    memcpy(mp.magic, RESPONDER_REPLY_MAGIC, sizeof(mp.magic));
    memcpy(mp.board_id_hex, my_board_id_hex, BOARD_ID_SIZE * 2);

    p = pbuf_alloc(PBUF_TRANSPORT, sizeof(responder_packet_t), PBUF_RAM);
    if (!p) {
        return;
    }
    memcpy(p->payload, &mp, sizeof(responder_packet_t));
    udp_sendto(pcb, p, addr, port);
    pbuf_free(p);
}

int wifi_settings_remote_set_two_stage_handler(
        uint8_t msg_type,
        handler_callback1_t callback1,
        handler_callback2_t callback2,
        void* arg) {
    uint8_t handler_id = msg_type - ID_FIRST_HANDLER;
    if (handler_id >= NUM_HANDLERS) {
        return PICO_ERROR_INVALID_ARG;
    }
    g_handler_table[(uint) handler_id].callback1 = callback1;
    g_handler_table[(uint) handler_id].callback2 = callback2;
    g_handler_table[(uint) handler_id].arg = arg;
    return PICO_ERROR_NONE;
}

int wifi_settings_remote_set_handler(
        uint8_t msg_type,
        handler_callback1_t callback,
        void* arg) {
    return wifi_settings_remote_set_two_stage_handler(msg_type, callback, NULL, arg);
}

void wifi_settings_remote_update_secret() {
    g_secret_valid = false;
    memset(g_secret_hashed, 0, HMAC_DIGEST_SIZE);

    uint8_t update_secret[128];
    uint update_secret_size = sizeof(update_secret);

    if (wifi_settings_get_value_for_key(
            "update_secret", (char*) update_secret, &update_secret_size)
    && (update_secret_size > 0)) {
        mbedtls_sha256_context ctx;
        mbedtls_sha256_init(&ctx);
        for (uint i = 0; i < 4096; i++) {
            if ((0 != mbedtls_sha256_starts_ret(&ctx, 0))
            || (0 != mbedtls_sha256_update_ret(&ctx, g_secret_hashed, HMAC_DIGEST_SIZE))
            || (0 != mbedtls_sha256_update_ret(&ctx, update_secret, update_secret_size))
            || (0 != mbedtls_sha256_finish_ret(&ctx, g_secret_hashed))) {
                panic("update_secret sha256 failed");
            }
        }
        mbedtls_sha256_free(&ctx);
        g_secret_valid = true;
    }
}

int wifi_settings_remote_init() {
    int pico_err = PICO_ERROR_NONE; 

    // We will be calling LWIP functions, so the lock is needed
    cyw43_arch_lwip_begin();
    if (g_remote_service_pcb) {
        goto end;
    }

    // Load secret
    wifi_settings_remote_update_secret();

    // Install handlers for messages
    wifi_settings_remote_set_handler(ID_PICO_INFO_HANDLER,
            wifi_settings_pico_info_handler, NULL);
    wifi_settings_remote_set_handler(ID_UPDATE_HANDLER,
            wifi_settings_update_handler, NULL);
    wifi_settings_remote_set_two_stage_handler(
            ID_UPDATE_REBOOT_HANDLER,
            NULL,
            wifi_settings_update_reboot_handler2, NULL);
#ifdef ENABLE_REMOTE_MEMORY_ACCESS
    wifi_settings_remote_set_handler(ID_READ_HANDLER,
            wifi_settings_read_handler, NULL);
    wifi_settings_remote_set_handler(ID_WRITE_FLASH_HANDLER,
            wifi_settings_write_flash_handler, NULL);
    wifi_settings_remote_set_two_stage_handler(
            ID_OTA_FIRMWARE_UPDATE_HANDLER,
            wifi_settings_ota_firmware_update_handler1,
            wifi_settings_ota_firmware_update_handler2, NULL);
#endif

    // Start TCP service
    struct tcp_pcb* port_pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    if (!port_pcb) {
        panic("wifi_settings_remote_init(): tcp_new_ip_type failed\n");
        pico_err = PICO_ERROR_INSUFFICIENT_RESOURCES;
        goto end;
    }

    err_t lwip_err = tcp_bind(port_pcb, NULL, PORT_NUMBER);
    if (lwip_err) {
        panic("wifi_settings_remote_init(): tcp_bind failed\n");
        pico_err = PICO_ERROR_RESOURCE_IN_USE;
        goto end;
    }

    g_remote_service_pcb = tcp_listen_with_backlog(port_pcb, 1);
    if (!g_remote_service_pcb) {
        panic("wifi_settings_remote_init(): tcp_listen_with_backlog failed\n");
        pico_err = PICO_ERROR_INSUFFICIENT_RESOURCES;
        goto end;
    }
    tcp_accept(g_remote_service_pcb, server_accept);

    // Start UDP service (responder)
    g_responder_service_pcb = udp_new_ip_type(IPADDR_TYPE_ANY);
    if (!g_responder_service_pcb) {
        panic("wifi_settings_remote_init(): udp_new_ip_type failed\n");
        pico_err = PICO_ERROR_INSUFFICIENT_RESOURCES;
        goto end;
    }
    lwip_err = udp_bind(g_responder_service_pcb, NULL, PORT_NUMBER);
    if (lwip_err) {
        panic("wifi_settings_remote_init(): udp_bind failed\n");
        pico_err = PICO_ERROR_INSUFFICIENT_RESOURCES;
        goto end;
    }
    udp_recv(g_responder_service_pcb, responder_recv, NULL);

    pico_err = PICO_ERROR_NONE; 
end:
    cyw43_arch_lwip_end();
    return pico_err;
}
