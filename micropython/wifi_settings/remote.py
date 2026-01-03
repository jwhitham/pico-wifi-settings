#!/usr/bin/env python
#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Remote update service for Micropython pico-wifi-settings.
#

import argparse
import asyncio
import hashlib
import os
import struct
import sys
import traceback
from asyncio import StreamReader, StreamWriter
from pathlib import Path
from abc import abstractmethod

# Type-checking
try:
    import typing
except ImportError:
    pass

PORT_NUMBER =               1404
RESPONDER_REQUEST_MAGIC =  b"PWS?"
RESPONDER_REPLY_MAGIC =    b"PWS:"
BOARD_ID_SIZE =             8 

CHALLENGE_SIZE =            15
AUTHENTICATION_SIZE =       15
AES_BLOCK_SIZE =            16
DATA_HASH_SIZE =            7
HMAC_BLOCK_SIZE =           64

ID_GREETING =               70      # s->c
ID_REQUEST =                71      # s<-c
ID_CHALLENGE =              72      # s->c
ID_AUTHENTICATION =         73      # s<-c
ID_RESPONSE =               74      # s->c
ID_ACKNOWLEDGE =            75      # s<-c
ID_OK =                     76      # s->c
ID_AUTH_ERROR =             77      # both
ID_VERSION_ERROR =          78      # both
ID_BAD_MSG_ERROR =          79      # both
ID_BAD_PARAM_ERROR =        80      # s->c
ID_BAD_HANDLER_ERROR =      81      # s->c
ID_NO_SECRET_ERROR =        82      # s->c
ID_CORRUPT_ERROR =          83      # s->c
ID_UNKNOWN_ERROR =          84      # s->c
ID_PICO_INFO_HANDLER =      120
ID_UPDATE_HANDLER =         121
ID_READ_HANDLER =           122
ID_RESERVED_3 =             123
ID_UPDATE_REBOOT_HANDLER =  124
ID_FLASH_WRITE_HANDLER =    125
ID_RESERVED_6 =             126
ID_OTA_FIRMWARE_UPDATE_HANDLER = 127
ID_FIRST_USER_HANDLER =     128
ID_LAST_USER_HANDLER =      143

ID_FIRST_HANDLER = ID_PICO_INFO_HANDLER
NUM_HANDLERS = ID_LAST_USER_HANDLER + 1 - ID_FIRST_HANDLER
HEADER_SIZE = AES_BLOCK_SIZE - DATA_HASH_SIZE

PROTOCOL_VERSION = 1
AES_IV = ZERO_BLOCK = b"\x00" * AES_BLOCK_SIZE
PAD_BLOCK_1 = b"\x00" * (AES_BLOCK_SIZE - 1)

# Magic number for CBC mode
# see https://github.com/micropython/micropython/blob/master/docs/library/cryptolib.rst
CIPHER_MODE = 2

# Note- the structure of a reply_header or request_header is as follows:
# typedef struct enc_message_header_t {
#    uint32_t    data_size;
#    int32_t     parameter_or_result;
#    uint8_t     msg_type;
#    uint8_t     data_hash[DATA_HASH_SIZE];
# } enc_message_header_t;
# The size of this structure should be AES_BLOCK_SIZE
HEADER_STRUCT = "<IIB7s"
HEADER_DATA_HASH_OFFSET = AES_BLOCK_SIZE - DATA_HASH_SIZE

def __unpack_header(header: bytes) -> typing.Tuple[int, int, int, bytes]:
    return struct.unpack(HEADER_STRUCT, header)

def __pack_header(data_size: int, parameter_or_result: int,
            msg_type: int, data_hash: bytes = ZERO_BLOCK[:DATA_HASH_SIZE]) -> bytes:
    return struct.pack(HEADER_STRUCT, header)

class ReceiveState:
    # Authentication states (unencrypted)
    SEND_GREETING = 1
    EXPECT_REQUEST = 2
    SEND_CHALLENGE = 3
    EXPECT_AUTHENTICATION = 4
    SEND_AUTHENTICATION = 5
    EXPECT_ACKNOWLEDGE = 6
    SEND_BAD_MSG_ERROR = 7
    SEND_AUTH_ERROR = 8
    SEND_NO_SECRET_ERROR = 9
    # Encrypted communication states
    EXPECT_ENC_REQUEST_HEADER = 10
    EXPECT_ENC_REQUEST_PAYLOAD = 11
    SEND_ENC_REPLY_HEADER = 12
    SEND_ENC_REPLY_PAYLOAD = 13
    SEND_CORRUPT_ERROR = 14
    SEND_BAD_PARAM_ERROR = 15
    SEND_BAD_HANDLER_ERROR = 16
    SEND_ENC_REPLY_HEADER_WITH_CALLBACK2 = 17
    # Special state when waiting to finish sending
    EXECUTE_CALLBACK2 = 18
    // Disconnected state
    DISCONNECT = 19


HandlerCallback1 = typing.Optional[typing.Callable[[int, bytes, int, typing.Any],
                                   typing.Tuple[bytes, int]]]
# (msg_type, request_data_buffer, input_parameter, arg) -> (reply_data_buffer, return_value)
HandlerCallback2 = typing.Optional[typing.Callable[[int, bytes, int, typing.Any]]]
# (msg_type, reply_data_buffer, return_value, arg) -> None

class HandlerCallbackArg:
    callback1: HandlerCallback1
    callback2: HandlerCallback2
    arg: typing.Any

g_handler_table: typing.List[HandlerCallbackArg] = [HandlerCallbackArg() for _ in range(NUM_HANDLERS)]
g_hmac_padded_key_1: bytes = b"\x00" * HMAC_DIGEST_SIZE
g_hmac_padded_key_2: bytes = b"\x00" * HMAC_DIGEST_SIZE
g_secret_valid: bool = False

class Session:
    data: bytes = b"" # MAX_DATA_SIZE
    client_challenge: bytes = b"" # CHALLENGE_SIZE
    server_challenge: bytes = b"" # CHALLENGE_SIZE
    output_block: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    output_block_ready: bool = False
    input_block: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    input_block_offset: int = 0
    decrypt: cryptolib.aes
    encrypt: cryptolib.aes
    reply_header: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    request_header: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    state: ReceiveState = ReceiveState.ID_GREETING
    data_index: int = 0


    def __generate_authentication(self, append_code: bytes) -> bytes:
        """Internal. Compute HMAC-SHA256. This can be done using the hmac module
        with Python 3 but this is not available on Micropython."""
        # first SHA256 start
        h1 = hashlib.sha256()
        # add padded key and message
        h1.update(g_hmac_padded_key_1)
        h1.update(self.client_challenge)
        h1.update(self.server_challenge)
        h1.update(append_code)
        # first SHA256 calculated
        d1 = h1.digest()

        # second SHA256 start
        h2 = hashlib.sha256()
        # add padded key and first SHA256
        h2.update(g_hmac_padded_key_2)
        h2.update(d1)
        # second SHA256 calculated - this is the HMAC-SHA256 result
        d2 = h2.digest()
        return d2

    def __generate_keys(self) -> None:
        """Internal. Generate encryption and decryption keys
        and Micropython cryptolib objects."""
        raw_key = self.__generate_authentication("SK")
        self.encrypt = cryptolib.aes(raw_key, CIPHER_MODE, AES_IV)

        raw_key = self.__generate_authentication("CK")
        self.decrypt = cryptolib.aes(raw_key, CIPHER_MODE, AES_IV)

    def __generate_enc_data_hash(self, header: bytes) -> bytes:
        """Internal. Generate and return a hash for the reply header and payload (if any).

        The first part of the header is hashed, ignoring the data hash bytes at the end.
        All payload data is hashed.
        The first DATA_HASH_SIZE bytes of the SHA-256 are returned.
        """
        h1 = hashlib.sha256()
        h1.update(header[:HEADER_DATA_HASH_OFFSET])
        h1.update(self.data)    # Note: data size expected to match header.data_size
        return h1.digest()[:DATA_HASH_SIZE]

    def __generate_enc_header_for_error(self, msg_type: int) -> None:
        """Internal. Generate an encrypted reply header containing the error msg_type.
        The result is stored in self.reply_header (clear) and self.output_block (encrypted)."""

        # Only the msg_type and data_hash fields are used - everything else is 0
        self.reply_header = self.__pack_header(0, 0, msg_type, self.__generate_enc_data_hash(
                                self.__pack_header(0, 0, msg_type)))

        # Encrypt
        self.output_block = self.encrypt.encrypt(self.reply_header)
        self.state = ReceiveState.DISCONNECT

    def __generate_clear_header_for_error(self, msg_type: int) -> None:
        """Internal. Generate an unencrypted reply header containing the error msg_type.
        The result is stored in self.output_block."""
        self.output_block = bytes([msg_type]) + ZERO_BLOCK[1:]
        self.state = ReceiveState.DISCONNECT

    def __generate_output_block(self) -> bool:
        """Internal. Generate an appropriate output for the current state
        and store it in self.output_block."""
        if self.state == ReceiveState.SEND_GREETING:
            # First message, server to client. Say hello.
            # (self.data contains a greeting message)
            self.output_block = self.data[self.data_index : self.data_index + AES_BLOCK_SIZE]
            self.data_index += AES_BLOCK_SIZE
            if self.data_index >= self.reply_header.data_size:
                self.state = ReceiveState.EXPECT_REQUEST
            return True
        elif self.state == ReceiveState.EXPECT_REQUEST:
            # Second message, client to server. Client sends the client challenge.
            return False
        elif self.state == ReceiveState.SEND_CHALLENGE:
            # Third message, server to client. Server sends the server challenge.
            self.output_block = bytes([ID_CHALLENGE]) + os.urandom(CHALLENGE_SIZE)
            self.state = ReceiveState.EXPECT_AUTHENTICATION
            return True
        elif self.state == ReceiveState.EXPECT_AUTHENTICATION:
            # Fourth message, client to server. Client sends the client authentication.
            return False
        elif self.state == ReceiveState.SEND_AUTHENTICATION:
            # Fifth message, server to client. Server sends the server authentication.
            self.output_block = bytes([ID_RESPONSE]) + self.__generate_authentication("SA")
            self.state = ReceiveState.EXPECT_ACKNOWLEDGE
            return True
        elif self.state == ReceiveState.EXPECT_ACKNOWLEDGE:
            # Sixth message, client to server. Client indicates authentication is complete.
            return False
        elif self.state == ReceiveState.SEND_BAD_MSG_ERROR:
            # Report bad message error to the client.
            self.__generate_clear_header_for_error(ID_BAD_MSG_ERROR)
            return True
        elif self.state == ReceiveState.SEND_AUTH_ERROR:
            # Report authentication error to the client.
            self.__generate_clear_header_for_error(ID_AUTH_ERROR)
            return True
        elif self.state == ReceiveState.SEND_NO_SECRET_ERROR:
            # Report 'no secret' error to the client.
            self.__generate_clear_header_for_error(ID_NO_SECRET_ERROR)
            return True
        elif self.state == ReceiveState.SEND_CORRUPT_ERROR:
            # Encrypted stage. Report corrupt encrypted data error to the client.
            self.__generate_enc_header_for_error(ID_CORRUPT_ERROR)
            return True
        elif self.state == ReceiveState.SEND_BAD_PARAM_ERROR:
            # Encrypted stage. Report bad parameter error to the client.
            self.__generate_enc_header_for_error(ID_BAD_PARAM_ERROR)
            return True
        elif self.state == ReceiveState.SEND_BAD_HANDLER_ERROR:
            # Encrypted stage. Report bad handler error to the client.
            self.__generate_enc_header_for_error(ID_BAD_HANDLER_ERROR)
            return True
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_HEADER:
            # Encrypted stage. Awaiting request from the client.
            return False
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD:
            # Encrypted stage. Awaiting payload from the client.
            return False
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER:
            # Encrypted stage. Send reply header to the client.
            self.output_block = self.encrypt.encrypt(self.reply_header)
            if len(self.data) == 0:
                # Header only - no payload
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
            else:
                self.state = ReceiveState.SEND_ENC_REPLY_PAYLOAD
            return True
        elif self.state == ReceiveState.SEND_ENC_REPLY_PAYLOAD:
            # Encrypted stage. Send payload data to the client.
            self.output_block = self.encrypt.encrypt(
                    self.data[self.data_index : self.data_index + AES_BLOCK_SIZE])
            self.data_index += AES_BLOCK_SIZE
            if self.data_index >= len(self.data):
                # Finished
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
            return True
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER_WITH_CALLBACK2:
            # Encrypted stage. Send reply header to the client (callback2 pending).
            self.output_block = self.encrypt.encrypt(self.reply_header)
            self.state = ReceiveState.EXECUTE_CALLBACK2
            return True
        elif self.state == ReceiveState.EXECUTE_CALLBACK2:
            # Execute callback2 handler when header has been sent (nothing should be sent).
            return False
        elif self.state == ReceiveState.DISCONNECT:
            return False
        return False

    def __handle_enc_request_end(self) -> None:
        """Internal. Process the end of an encrypted request,
        i.e. verify integrity, call a handler, prepare to send reply data."""

        # Check data hash is correct
        expect_hash = self.__generate_enc_data_hash(self.request_header)
        if expect_hash != self.request_header[ENC_HEADER_DATA_HASH_OFFSET:]:
            self.state = ReceiveState.SEND_CORRUPT_ERROR
            return

        # Process the request, getting new data, data_size, parameter
        (_, parameter, msg_type, _) = __unpack_header(self.request_header)
        handler_id = msg_type - ID_FIRST_HANDLER

        # Check handler is valid (this was already checked, but g_handler_table may have changed)
        if ((handler_id >= NUM_HANDLERS)
        or (handler_id < 0)
        or not (g_handler_table[handler_id].callback1
                or g_handler_table[handler_id].callback2)):
            self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
            return

        self.data = b""
        result = 0

        if g_handler_table[handler_id].callback1:
            # call first handler
            return_value = g_handler_table[handler_id].callback1(
                    msg_type, self.data, parameter, g_handler_table[handler_id].arg)
            # expect a return like (reply_data_buffer, return_value)
            if ((type(return_value) != tuple)
            or (len(return_value) != 2)
            or (type(return_value[0]) != bytes)
            or (type(return_value[1]) != int)):
                self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
                return
            self.data = return_value[0]
            result = return_value[1]

            # Limit data size as the C implementation does
            if len(self.data) > MAX_DATA_SIZE:
                self.data = self.data[:MAX_DATA_SIZE]

        self.data_index = 0

        if g_handler_table[handler_id].callback2:
            # prepare to call the second handler; no data will be sent via the network,
            # but it will be available for callback2. The request header is repacked with
            # new information to be used by callback2.
            self.request_header = __pack_header(len(self.data), result, ID_OK)
            self.state = ReceiveState.SEND_ENC_REPLY_HEADER_WITH_CALLBACK2
            reply_data_size = 0
        else:
            # no second handler, return data
            self.state = ReceiveState.SEND_ENC_REPLY_HEADER
            reply_data_size = len(self.data)

        # Generate reply header
        self.reply_header = self.__pack_header(reply_data_size, result, ID_OK,
            self.__generate_enc_data_hash(self.__pack_header(reply_data_size, result, ID_OK)))

    def __handle_enc_request_start(self) -> None:
        """Internal. Process the start of an encrypted request,
        i.e. check the header and start the input data transfer."""
        # Decrypt 
        self.request_header = self.decrypt.decrypt(self.input_block)

        # Check handler ID is within the allowed range
        (data_size, parameter, msg_type, _) = __unpack_header(self.request_header)
        handler_id = msg_type - ID_FIRST_HANDLER
        if ((handler_id >= NUM_HANDLERS)
        or (handler_id < 0)
        or not (g_handler_table[handler_id].callback1
                or g_handler_table[handler_id].callback2)) {
            self.state = SEND_BAD_HANDLER_ERROR
            return

        # Check parameters are valid, start processing the request
        if data_size > MAX_DATA_SIZE: {
            self.state = SEND_BAD_PARAM_ERROR
            return

        # Prepare for receiving the request payload
        self.data = b""
        if data_size == 0:
            # There is no payload - go direct to the end
            self.__handle_enc_request_end()
        else:
            # Payload needed
            self.state = ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD

    def __handle_enc_request_add_data(self) -> None:
        """Internal. Process data input for an encrypted request."""
        self.data += self.decrypt.decrypt(self.input_block)
        (data_size, _, _, _) = __unpack_header(self.request_header)
        if len(self.data) >= data_size:
            # No more blocks
            self.__handle_enc_request_end()

    def __handle_input_block(self) -> bool:
        """Internal. Handle the input appropriately for the current state."""
        if self.state == ReceiveState.SEND_GREETING:
            # First message, server to client. Say hello.
            return False
        elif self.state == ReceiveState.EXPECT_REQUEST:
            # Second message, client to server. Client sends the client challenge.
            if self.input_block[0] != ID_REQUEST:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            elif not g_secret_valid: {
                self.state = ReceiveState.SEND_NO_SECRET_ERROR
            else:
                self.client_challenge = self.input_block[1:]
                self.state = ReceiveState.SEND_CHALLENGE
            }
            return True
        elif self.state == ReceiveState.SEND_CHALLENGE:
            # Third message, server to client. Server sends the server challenge.
            return False
        elif self.state == ReceiveState.EXPECT_AUTHENTICATION:
            # Fourth message, client to server. Client sends the client authentication.
            if block[0] != ID_AUTHENTICATION:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            else:
                check_authentication = self.__generate_authentication("CA")
                if check_authentication != block[1:]:
                    self.state = ReceiveState.SEND_AUTH_ERROR
                else:
                    self.state = ReceiveState.SEND_AUTHENTICATION
            return True
        elif self.state == ReceiveState.SEND_AUTHENTICATION:
            # Fifth message, server to client. Server sends the server authentication.
            return False
        elif self.state == ReceiveState.EXPECT_ACKNOWLEDGE:
            # Sixth message, client to server. Client indicates authentication is complete.
            if block[0] != ID_ACKNOWLEDGE:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            else:
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
                # Session keys can be generated now
                self.__generate_keys()
            return True
        elif self.state == ReceiveState.SEND_BAD_MSG_ERROR:
            # Report bad message error to the client.
            return False
        elif self.state == ReceiveState.SEND_BAD_PARAM_ERROR:
            # Report bad request parameter error to the client.
            return False
        elif self.state == ReceiveState.SEND_BAD_HANDLER_ERROR:
            # Report bad handler error to the client.
            return False
        elif self.state == ReceiveState.SEND_AUTH_ERROR:
            # Report authentication error to the client.
            return False
        elif self.state == ReceiveState.SEND_NO_SECRET_ERROR:
            # Report "no secret" error to the client.
            return False
        elif self.state == ReceiveState.SEND_CORRUPT_ERROR:
            # Report corrupt block error to the client.
            return False
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_HEADER:
            # Encrypted stage. Awaiting request from the client.
            self.__handle_enc_request_start()
            return True
        elif self.state == ReceiveState.EXECUTE_CALLBACK2:
            # Execute callback2 handler when header has been sent (nothing should be received).
            return False
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD:
            # Encrypted stage. Awaiting payload data from the client.
            self.__handle_enc_request_add_data()
            return True
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER:
            # Encrypted stage. Send reply header to the client.
            return False
        elif self.state == ReceiveState.SEND_ENC_REPLY_PAYLOAD:
            # Encrypted stage. Send payload data to the client.
            return False
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER_WITH_CALLBACK2:
            # Encrypted stage. Send reply header to the client (callback2 handler pending).
            return False
        elif self.state == ReceiveState.DISCONNECT:
            return False
        return False

# EDIT HORIZON
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
        if (!self.output_block_ready) {
            // try to generate an output block
            if (!generate_output_block(session)) {
                // There's nothing to send
                return;
            }
            self.output_block_ready = true;
        }

        // try to send a block
        // Note: can't use tcp_sndbuf to tell if this will succeed, so we have
        // to generate a block beforehand.
        err_t err = tcp_write(client_pcb, self.output_block,
                        AES_BLOCK_SIZE, TCP_WRITE_FLAG_COPY);
        if (err == ERR_OK) {
            // success, block has been sent
            self.output_block_ready = false;
        } else if (err == ERR_MEM) {
            // failure, we should try again later, after some data has been sent
            return;
        } else {
            // some other error - abandon the connection
            self.state = DISCONNECT;
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
        self.input_block[(uint) self.input_block_offset] = payload[(uint) recv_index];
        self.input_block_offset++;
        if (self.input_block_offset >= AES_BLOCK_SIZE) {
            // Process the block
            if (!handle_input_block(session)) {
                // Unable to handle input right now!
                // (There is no buffer space for this.)
                // We will disconnect, possibly after sending an error message
                input_buffer_overflow = true;
                break;
            }
            self.input_block_offset = 0;
        }
    }

    // mark data as received, free pbuf
    tcp_recved(client_pcb, payload_size);
    pbuf_free(p);

    // disconnect before sending anything if requested by handle_input_block
    if (self.state == DISCONNECT) {
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
        self.state = DISCONNECT;
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

    if (self.state == EXECUTE_CALLBACK2) {
        // Data has been sent, execute callback2 if it exists (close first)
        server_tcp_close(client_pcb);

        uint8_t handler_id = self.request_header.msg_type - ID_FIRST_HANDLER;

        if ((handler_id < NUM_HANDLERS)
        && (g_handler_table[(uint) handler_id].callback2)) {
            g_handler_table[(uint) handler_id].callback2(
                self.request_header.msg_type,
                self.data,
                self.request_header.data_size,
                self.request_header.parameter_or_result,
                g_handler_table[(uint) handler_id].arg);
        }
        // Result of executing callback2 cannot be reported
        free(session);
    } else if (self.state == DISCONNECT) {
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
    int string_size = snprintf((char*) self.data, MAX_DATA_SIZE,
        "xxx\r%s\rpico-wifi-settings version " WIFI_SETTINGS_VERSION_STRING "\r\n",
        wifi_settings_get_board_id_hex());
    // bytes 0 .. 2 are fixed fields in the reply:
    self.data[0] = ID_GREETING;
    self.data[1] = PROTOCOL_VERSION;
    self.data[2] = (uint8_t) ((string_size + AES_BLOCK_SIZE - 1) / AES_BLOCK_SIZE);
    // bytes 4 .. 19 contain the board ID in uppercase hex format
    self.reply_header.data_size = ((uint32_t) self.data[2]) * AES_BLOCK_SIZE;
    // bytes 20 .. <unspecified> contain UTF-8 text that can be printed

    self.state = SEND_GREETING;
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
    memset(secret_hashed, 0, HMAC_DIGEST_SIZE);

    uint8_t update_secret[128];
    uint update_secret_size = sizeof(update_secret);

    if (wifi_settings_get_value_for_key(
            "update_secret", (char*) update_secret, &update_secret_size)
    && (update_secret_size > 0)) {
        mbedtls_sha256_context ctx;
        mbedtls_sha256_init(&ctx);
        for (uint i = 0; i < 4096; i++) {
            if ((0 != mbedtls_sha256_starts(&ctx, 0))
            || (0 != mbedtls_sha256_update(&ctx, secret_hashed, HMAC_DIGEST_SIZE))
            || (0 != mbedtls_sha256_update(&ctx, update_secret, update_secret_size))
            || (0 != mbedtls_sha256_finish(&ctx, secret_hashed))) {
                panic("update_secret sha256 failed");
            }
        }
        mbedtls_sha256_free(&ctx);
        g_hmac_padded_key_1 = (bytes([k ^ 0x36 for k in secret_hashed])
                + bytes([0x36 for _ in range(HMAC_BLOCK_SIZE - HMAC_DIGEST_SIZE)]))
        g_hmac_padded_key_2 = (bytes([k ^ 0x5c for k in secret_hashed])
                + bytes([0x5c for _ in range(HMAC_BLOCK_SIZE - HMAC_DIGEST_SIZE)]))
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
            wifi_settings_update_reboot_handler1,
            wifi_settings_update_reboot_handler2, NULL);
    bi_decl_if_func_used(bi_program_feature("pico-wifi-settings remote file updates"));
#ifdef ENABLE_REMOTE_MEMORY_ACCESS
    wifi_settings_remote_set_handler(ID_READ_HANDLER,
            wifi_settings_read_handler, NULL);
    wifi_settings_remote_set_handler(ID_WRITE_FLASH_HANDLER,
            wifi_settings_write_flash_handler, NULL);
    wifi_settings_remote_set_two_stage_handler(
            ID_OTA_FIRMWARE_UPDATE_HANDLER,
            wifi_settings_ota_firmware_update_handler1,
            wifi_settings_ota_firmware_update_handler2, NULL);
    bi_decl_if_func_used(bi_program_feature("pico-wifi-settings remote memory access"));
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

def __hmac_sha256(key: bytes, msg: bytes) -> bytes:
    """Internal. Compute HMAC-SHA256. This can be done using the hmac module
    with Python 3 but this is not available on Micropython."""
    # first SHA256 start
    h1 = hashlib.sha256()
    assert len(key) < HMAC_BLOCK_SIZE
    # add padded key
    h1.update(bytes([k ^ 0x36 for k in key]))
    h1.update(bytes([0x36 for _ in range(HMAC_BLOCK_SIZE - len(key))]))
    # add message
    h1.update(msg)
    # first SHA256 calculated
    d1 = h1.digest()

    # second SHA256 start
    h2 = hashlib.sha256()
    # add padded key
    h2.update(bytes([k ^ 0x5c for k in key]))
    h2.update(bytes([0x5c for _ in range(HMAC_BLOCK_SIZE - len(key))]))
    # add first SHA256
    h2.update(d1)
    # second SHA256 calculated - this is the HMAC-SHA256 result
    d2 = h2.digest()
    return d2

def __get_pad_bytes(data_size: int, block_size: int, pad_byte = b"\x00") -> bytes:
    """Pad data so that it is a multiple of block_size."""
    last_block_size = data_size % block_size
    if last_block_size == 0:
        return b""
    pad = block_size - last_block_size
    return pad_byte * pad





class RemoteError(Exception):
    """Base for all errors relating to issues with the remote system."""
    pass

class BadMessageError(RemoteError):
    """Indicates an invalid request was received during the
    unencrypted communication stage."""
    def __init__(self, received_msg_type: int, expected_msg_type: int) -> None:
        RemoteError.__init__(self)
        self.received_msg_type = received_msg_type
        self.expected_msg_type = expected_msg_type

    def __str__(self) -> str:
        return (f"BadMessageError(received {self.received_msg_type} " +
                f"expected {self.expected_msg_type})")

class BadVersionError(RemoteError):
    """Indicates an invalid version number was received during the
    unencrypted communication stage."""
    def __init__(self, version: int) -> None:
        RemoteError.__init__(self)
        self.version = version

    def __str__(self) -> str:
        return f"BadVersionError({self.version})"

class AuthenticationError(RemoteError):
    """Indicates that the client and server don't share the same update secret."""
    def __str__(self) -> str:
        return ("AuthenticationError: the given --secret "
            "does not match the update_secret on the board")

class CorruptedMessageError(RemoteError):
    """Indicates corruption in the encrypted communication stage."""
    def __init__(self, hint: str) -> None:
        RemoteError.__init__(self)
        self.hint = hint

    def __str__(self) -> str:
        return f"CorruptedMessageError({self.hint})"

class AbstractCommunication:
    def __init__(self, update_secret_hash: bytes,
            reader: StreamReader, writer: StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.update_secret_hash = update_secret_hash
        self.enc_receive: typing.Any = None
        self.enc_transmit: typing.Any = None

    def gen_auth(self, session_data: bytes) -> bytes:
        """Generate authentication code from secret and session data."""
        return __hmac_sha256(key=self.update_secret_hash, msg=session_data)

    def get_data_hash(self, data: bytes, header: bytes) -> bytes:
        """Compute hash for a message."""
        integrity = hashlib.sha256()
        integrity.update(header)
        integrity.update(data)
        return integrity.digest()[:DATA_HASH_SIZE]

    @abstractmethod
    async def greeting(self) -> None:
        """First message, server to client. Say hello."""
        pass

    @abstractmethod
    async def request(self) -> bytes:
        """Second message, client to server. Client sends the client challenge."""
        pass

    @abstractmethod
    async def challenge(self) -> bytes:
        """Third message, server to client. Server sends the server challenge."""
        pass

    @abstractmethod
    async def authentication(self, client_authentication: bytes) -> None:
        """Fourth message, client to server. Client sends the client authentication."""
        pass

    @abstractmethod
    async def response(self, server_authentication: bytes) -> None:
        """Fifth message, server to client. Server sends the server authentication."""
        pass

    @abstractmethod
    async def acknowledge(self) -> None:
        """Sixth message, client to server. Client indicates authentication is complete."""
        pass

    async def setup(self) -> None:
        """Setup process.

        This will either raise an exception or complete successfully.
        If completed successfully, self.enc_receive and self.enc_transmit will be
        ready for use, and self.receive() and self.transmit() can be used.
        """
        try:
            # Server says hello
            await self.greeting()

            # Client and server challenge each other
            client_challenge = await self.request()
            server_challenge = await self.challenge()

            # Client and server must exchange authentication codes (based
            # on both challenges and the shared secret). AuthenticationError is
            # raised if there is any error here.
            client_authentication = self.gen_auth(client_challenge +
                        server_challenge + b"CA")[:AUTHENTICATION_SIZE]
            server_authentication = self.gen_auth(client_challenge +
                        server_challenge + b"SA")[:AUTHENTICATION_SIZE]
            await self.authentication(client_authentication)
            await self.response(server_authentication)

            # Client acknowledges that the authentication was ok
            await self.acknowledge()

        except AuthenticationError:
            # Authentication error detected during setup
            await self.write_block(struct.pack("<B", ID_AUTH_ERROR) + PAD_BLOCK_1)
            raise

        except BadVersionError:
            # version error detected during setup
            await self.write_block(struct.pack("<B", ID_VERSION_ERROR) + PAD_BLOCK_1)
            raise

        except BadMessageError as e:
            # Report errors from the other side
            if e.received_msg_type == ID_AUTH_ERROR:
                # Authentication error reported from the other side
                raise AuthenticationError() from None
            elif e.received_msg_type == ID_VERSION_ERROR:
                # Version error reported from the other side
                raise BadVersionError(0) from None
            else:
                # Bad message detected on this side
                await self.write_block(struct.pack("<B", ID_BAD_MSG_ERROR) + PAD_BLOCK_1)
                raise

        except asyncio.IncompleteReadError:
            raise

        # Setup is complete - the rest of the packets will be encrypted
        # with the agreed session keys, which will be generated now based
        # on the challenges which were sent, along with the shared secret
        self.setup_aes(client_challenge, server_challenge)

    async def write_block(self, data: bytes) -> None:
        """Write a whole number of blocks."""
        assert (len(data) % AES_BLOCK_SIZE) == 0
        self.writer.write(data)
        await self.writer.drain()

    async def read_block(self) -> bytes:
        """Read one block."""
        return await self.reader.readexactly(AES_BLOCK_SIZE)

    @abstractmethod
    def setup_aes(self, client_challenge: bytes, server_challenge: bytes) -> None:
        """Generate AES keys."""
        pass

    def get_c2s_key(self, client_challenge: bytes, server_challenge: bytes) -> bytes:
        """Generate AES client to server key."""
        return self.gen_auth(client_challenge + server_challenge + b"CK")

    def get_s2c_key(self, client_challenge: bytes, server_challenge: bytes) -> bytes:
        """Generate AES server to client key."""
        return self.gen_auth(client_challenge + server_challenge + b"SK")

    @abstractmethod
    def validate(self, msg_type: int, data_size: int, parameter: int) -> None:
        """Raise an exception if the request is invalid."""
        pass

    async def receive(self) -> typing.Tuple[int, bytes, int]:
        """Receive an encrypted message from the other side.

        This will either raise an exception or complete successfully.
        The return value is the message received:
        (msg_type, result_data, result_value)

        This is after integrity checking and validation.
        The message received will be validated by calling self.validate()
        before receiving data.

        Exceptions include:
            asyncio.IncompleteReadError  - disconnected
            CorruptedMessageError
            anything from self.validate()

        """

        assert self.enc_receive is not None

        # Read and decrypt an encrypted header block
        clear_block = self.enc_receive.decrypt(await self.read_block())

        # Header block contains the message type and its result value
        header = clear_block[:HEADER_SIZE]
        (data_size, result_value, msg_type) = struct.unpack("<IiB", header)
        data_hash = clear_block[HEADER_SIZE:]

        # Validate parameters
        self.validate(msg_type, data_size, result_value)

        # Process input blocks for the handler
        blocks: typing.List[bytes] = []
        num_blocks = (data_size + AES_BLOCK_SIZE - 1) // AES_BLOCK_SIZE
        while len(blocks) < num_blocks:
            enc_block = await self.read_block()
            blocks.append(self.enc_receive.decrypt(enc_block))

        # Reassemble and check integrity
        result_data = b"".join(blocks)[:data_size]
        if data_hash != self.get_data_hash(result_data, header):
            raise CorruptedMessageError("Reply hash incorrect")

        return (msg_type, result_data, result_value)

    async def transmit(self, msg_type: int, request_data: bytes, parameter: int) -> None:
        """Transmit an encrypted message to the other side."""

        assert self.enc_transmit is not None

        # Send header
        header = struct.pack("<IiB", len(request_data), parameter, msg_type)
        data_hash = self.get_data_hash(request_data, header)
        clear_block = header + data_hash
        assert len(clear_block) == AES_BLOCK_SIZE
        blocks = [self.enc_transmit.encrypt(clear_block)]

        # Pad data to block boundary
        request_data += __get_pad_bytes(len(request_data), AES_BLOCK_SIZE)

        # Add data
        num_blocks = len(request_data) // AES_BLOCK_SIZE
        for i in range(num_blocks):
            clear_block = request_data[i * AES_BLOCK_SIZE : (i + 1) * AES_BLOCK_SIZE]
            blocks.append(self.enc_transmit.encrypt(clear_block))

        # Send
        await self.write_block(b"".join(blocks))

class Server(AbstractCommunication):
    """Communications specialisation for server side."""

    def __init__(self,
            handlers: typing.Dict[int, HandlerCallback],
            update_secret: bytes,
            reader: StreamReader, writer: StreamWriter) -> None:
        AbstractCommunication.__init__(self, update_secret, reader, writer)
        self.handlers = handlers

    async def greeting(self) -> None:
        """First message, server to client. Say hello."""
        data = struct.pack("<BBB", ID_GREETING,
                        PROTOCOL_VERSION, 0) + GREETING
        data += get_pad_bytes(len(data), AES_BLOCK_SIZE)
        num_blocks = len(data) // AES_BLOCK_SIZE
        data = struct.pack("<BBB", ID_GREETING,
                        PROTOCOL_VERSION, num_blocks) + data[3:]
        await self.write_block(data)

    async def request(self) -> bytes:
        """Second message, client to server. Client sends the client challenge."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != ID_REQUEST:
            raise BadMessageError(msg_type, ID_REQUEST)
        client_challenge = block[1:]
        return client_challenge

    async def challenge(self) -> bytes:
        """Third message, server to client. Server sends the server challenge."""
        server_challenge = os.urandom(CHALLENGE_SIZE)
        await self.write_block(struct.pack("<B", ID_CHALLENGE) + server_challenge)
        return server_challenge

    async def authentication(self, client_authentication: bytes) -> None:
        """Fourth message, client to server. Client sends the client authentication."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != ID_AUTHENTICATION:
            raise BadMessageError(msg_type, ID_AUTHENTICATION)

        if client_authentication != block[1:]:
            raise AuthenticationError()

    async def response(self, server_authentication: bytes) -> None:
        """Fifth message, server to client. Server sends the server authentication."""
        await self.write_block(struct.pack("<B", ID_RESPONSE) + server_authentication)

    async def acknowledge(self) -> None:
        """Sixth message, client to server. Client indicates authentication is complete."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != ID_ACKNOWLEDGE:
            raise BadMessageError(msg_type, ID_ACKNOWLEDGE)

    def setup_aes(self, client_challenge: bytes, server_challenge: bytes) -> None:
        """Generate AES keys for server."""
        self.enc_receive = cryptolib.aes(self.get_s2c_key(
                client_challenge, server_challenge), CIPHER_MODE, AES_IV)
        self.enc_transmit = cryptolib.aes(self.get_c2s_key(
                client_challenge, server_challenge), CIPHER_MODE, AES_IV)

    def validate(self, msg_type: int, data_size: int, parameter: int) -> None:
        """Raise an exception if the request is invalid."""
        if msg_type < ID_FIRST_HANDLER:
            raise BadHandlerError()
        handler = self.handlers.get(msg_type, None)
        if handler is None:
            raise BadHandlerError()

    async def run(self) -> None:
        """Run server."""
        try:
            await self.setup()
        except asyncio.IncompleteReadError:
            # Client has disappeared
            return
        except ConnectionResetError:
            # Connection lost
            return

        while True:
            result_data = b""
            result_value = 0
            msg_type = ID_CORRUPT_ERROR
            try:
                (msg_type, request_data, parameter) = await self.receive()
                handler = self.handlers[msg_type]
                (result_data, result_value) = await handler.callback1(request_data, parameter)
                msg_type = ID_OK
                if handler.two_stage_handler:
                    # No data is returned, all data is passed to callback2
                    result_data = b""

            except CorruptedMessageError as e:
                msg_type = ID_CORRUPT_ERROR
                raise
            except BadHandlerError as e:
                msg_type = ID_BAD_HANDLER_ERROR
                raise
            except BadParameterError as e:
                msg_type = ID_BAD_PARAM_ERROR
                raise
            except asyncio.IncompleteReadError:
                # Client has disappeared
                return
            except ConnectionResetError:
                # Connection lost
                return
            except Exception as e:
                msg_type = ID_UNKNOWN_ERROR
                raise
            finally:
                # Send reply (possibly an error)
                await self.transmit(msg_type, result_data, result_value)

            # If there was no error and deferred mode was used
            if handler.two_stage_handler:
                await handler.callback2(result_data, result_value)

def __update_secret_hash(self) -> bytes:
    """Turn the secret provided by the user into a 32-byte hash.

    This is derived from the update_secret= option in the wifi-settings file
    """
    update_secret_text = storage.get_value_for_key("update_secret")
    if not update_secret_text:
        # If there is no update_secret then the remote service is disabled
        return b""

    secret_hash = b"\x00" * 32
    secret_bytes = self.update_secret_text.encode("utf-8")
    for i in range(4096):
        secret_hash = hashlib.sha256(secret_hash + secret_bytes).digest()

    return secret_hash

def start_server() -> bool:
    update_secret_hash = __update_secret_hash()
    if not update_secret_hash:
        # If there is no update_secret then the remote service is disabled
        return

    # EDIT HORIZON

    async def serve_callback(reader: StreamReader, writer: StreamWriter) -> None:
        try:
            await Server(handlers, update_secret_hash, reader, writer).run()
        except FakeRebootError:
            server[0].close()
        except KeyboardInterrupt:
            server[0].close()
        except Exception as e:
            print("** TEST SERVER EXCEPTION:", str(e), file=sys.stderr)
            traceback.print_exc()
            print("** END OF EXCEPTION REPORT", file=sys.stderr)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server.append(await asyncio.start_server(serve_callback, SERVER_ADDRESS))
    await server[0].start_serving()
    port = server[0].sockets[0].getsockname()[1]

    return (server[0], port)

