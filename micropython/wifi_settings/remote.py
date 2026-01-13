#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Remote update service for Micropython pico-wifi-settings.
#

import hashlib
import os
import socket
import struct

import cryptolib  # type: ignore
from . import hostname, configuration, remote_handlers, storage

# Type-checking
try:
    import typing
except ImportError:
    pass


PORT_NUMBER =               1404
RESPONDER_REQUEST_MAGIC =  b"PWS?"
RESPONDER_REPLY_MAGIC =    b"PWS:"
BOARD_ID_SIZE =             8 
RESPONDER_MAX_SIZE =        20
MAX_DATA_SIZE =             4096

CHALLENGE_SIZE =            15
AUTHENTICATION_SIZE =       15
AES_BLOCK_SIZE =            16
DATA_HASH_SIZE =            7
HMAC_BLOCK_SIZE =           64
HMAC_DIGEST_SIZE =          32

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
DEBUG_HANDLERS = True

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
HEADER_STRUCT = "<IiB7s"
HEADER_DATA_HASH_OFFSET = AES_BLOCK_SIZE - DATA_HASH_SIZE

def __unpack_header(header: bytes):
    # return type is typing.Tuple[int, int, int, bytes]
    return struct.unpack(HEADER_STRUCT, header)

def __pack_header(data_size: int, parameter_or_result: int,
            msg_type: int, data_hash: bytes = ZERO_BLOCK[:DATA_HASH_SIZE]) -> bytes:
    return struct.pack(HEADER_STRUCT, data_size, parameter_or_result, msg_type, data_hash)

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
    # Disconnected state
    DISCONNECT = 19


class HandlerCallbackArg:
    callback1: remote_handlers.HandlerCallback1
    callback2: remote_handlers.HandlerCallback2
    arg: typing.Any

    def __init__(self, 
            callback1: remote_handlers.HandlerCallback1,
            callback2: remote_handlers.HandlerCallback2,
            arg: typing.Any) -> None:
        self.callback1 = callback1
        self.callback2 = callback2
        self.arg = arg

g_handler_table: typing.Dict[int, HandlerCallbackArg] = {}
g_hmac_padded_key_1: bytes = b"\x00" * HMAC_DIGEST_SIZE
g_hmac_padded_key_2: bytes = b"\x00" * HMAC_DIGEST_SIZE
g_secret_valid: bool = False
g_remote_service_greeting: bytes = b""
g_responder_reply_bytes: bytes = b""
g_remote_socket: typing.Optional[socket.socket] = None
g_responder_socket: typing.Optional[socket.socket] = None

class Session:
    data: bytearray # MAX_DATA_SIZE
    client_challenge: bytes = b"" # CHALLENGE_SIZE
    server_challenge: bytes = b"" # CHALLENGE_SIZE
    output_block: bytes = b"" # AES_BLOCK_SIZE
    input_block: bytes = b"" # AES_BLOCK_SIZE
    decrypt: cryptolib.aes
    encrypt: cryptolib.aes
    reply_header: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    request_header: bytes = ZERO_BLOCK # AES_BLOCK_SIZE
    state: int = ReceiveState.SEND_GREETING
    data_index: int = 0
    data_size: int = 0

    def __init__(self) -> None:
        """Allocate memory to support one connection - set up a greeting."""
        self.data = bytearray(MAX_DATA_SIZE)
        self.data_size = len(g_remote_service_greeting)
        self.data[:self.data_size] = g_remote_service_greeting
        self.state = ReceiveState.SEND_GREETING

    def generate_authentication(self, append_code: bytes) -> bytes:
        """Compute HMAC-SHA256. This can be done using the hmac module
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

    def generate_keys(self) -> None:
        """Generate encryption and decryption keys
        and Micropython cryptolib objects."""
        raw_key = self.generate_authentication(b"SK")
        self.encrypt = cryptolib.aes(raw_key, CIPHER_MODE, AES_IV)

        raw_key = self.generate_authentication(b"CK")
        self.decrypt = cryptolib.aes(raw_key, CIPHER_MODE, AES_IV)

    def generate_enc_data_hash(self, header: bytes, data: bytes) -> bytes:
        """Generate and return a hash for the reply header and payload (if any).

        The first part of the header is hashed, ignoring the data hash bytes at the end.
        All provided data is hashed.
        The first DATA_HASH_SIZE bytes of the SHA-256 are returned.
        """
        h1 = hashlib.sha256()
        h1.update(header[:HEADER_DATA_HASH_OFFSET])
        h1.update(data)
        return h1.digest()[:DATA_HASH_SIZE]

    def generate_enc_header_for_error(self, msg_type: int) -> None:
        """Generate an encrypted reply header containing the error msg_type.
        The result is stored in self.reply_header (clear) and self.output_block (encrypted)."""

        # Only the msg_type and data_hash fields are used - everything else is 0
        self.reply_header = __pack_header(0, 0, msg_type, self.generate_enc_data_hash(
                                __pack_header(0, 0, msg_type), b""))

        # Encrypt
        self.output_block = self.encrypt.encrypt(self.reply_header)
        self.state = ReceiveState.DISCONNECT

    def generate_clear_header_for_error(self, msg_type: int) -> None:
        """Generate an unencrypted reply header containing the error msg_type.
        The result is stored in self.output_block."""
        self.output_block = bytes([msg_type]) + ZERO_BLOCK[1:]
        self.state = ReceiveState.DISCONNECT

    def generate_output_block(self) -> None:
        """Generate an appropriate output for the current state
        and store it in self.output_block."""
        if self.state == ReceiveState.SEND_GREETING:
            # First message, server to client. Say hello.
            # (self.data contains a greeting message)
            self.output_block = self.data[self.data_index : self.data_index + AES_BLOCK_SIZE]
            self.data_index += AES_BLOCK_SIZE
            if self.data_index >= self.data_size:
                self.state = ReceiveState.EXPECT_REQUEST
        elif self.state == ReceiveState.EXPECT_REQUEST:
            # Second message, client to server. Client sends the client challenge.
            pass
        elif self.state == ReceiveState.SEND_CHALLENGE:
            # Third message, server to client. Server sends the server challenge.
            self.server_challenge = os.urandom(CHALLENGE_SIZE)
            self.output_block = bytes([ID_CHALLENGE]) + self.server_challenge
            self.state = ReceiveState.EXPECT_AUTHENTICATION
        elif self.state == ReceiveState.EXPECT_AUTHENTICATION:
            # Fourth message, client to server. Client sends the client authentication.
            pass
        elif self.state == ReceiveState.SEND_AUTHENTICATION:
            # Fifth message, server to client. Server sends the server authentication.
            self.output_block = (bytes([ID_RESPONSE]) +
                self.generate_authentication(b"SA")[:CHALLENGE_SIZE])
            self.state = ReceiveState.EXPECT_ACKNOWLEDGE
        elif self.state == ReceiveState.EXPECT_ACKNOWLEDGE:
            # Sixth message, client to server. Client indicates authentication is complete.
            pass
        elif self.state == ReceiveState.SEND_BAD_MSG_ERROR:
            # Report bad message error to the client.
            self.generate_clear_header_for_error(ID_BAD_MSG_ERROR)
        elif self.state == ReceiveState.SEND_AUTH_ERROR:
            # Report authentication error to the client.
            self.generate_clear_header_for_error(ID_AUTH_ERROR)
        elif self.state == ReceiveState.SEND_NO_SECRET_ERROR:
            # Report 'no secret' error to the client.
            self.generate_clear_header_for_error(ID_NO_SECRET_ERROR)
        elif self.state == ReceiveState.SEND_CORRUPT_ERROR:
            # Encrypted stage. Report corrupt encrypted data error to the client.
            self.generate_enc_header_for_error(ID_CORRUPT_ERROR)
        elif self.state == ReceiveState.SEND_BAD_PARAM_ERROR:
            # Encrypted stage. Report bad parameter error to the client.
            self.generate_enc_header_for_error(ID_BAD_PARAM_ERROR)
        elif self.state == ReceiveState.SEND_BAD_HANDLER_ERROR:
            # Encrypted stage. Report bad handler error to the client.
            self.generate_enc_header_for_error(ID_BAD_HANDLER_ERROR)
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_HEADER:
            # Encrypted stage. Awaiting request from the client.
            pass
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD:
            # Encrypted stage. Awaiting payload from the client.
            pass
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER:
            # Encrypted stage. Send reply header to the client.
            self.output_block = self.encrypt.encrypt(self.reply_header)
            if self.data_size == 0:
                # Header only - no payload
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
            else:
                self.state = ReceiveState.SEND_ENC_REPLY_PAYLOAD
        elif self.state == ReceiveState.SEND_ENC_REPLY_PAYLOAD:
            # Encrypted stage. Send payload data to the client.
            self.output_block = self.encrypt.encrypt(
                    self.data[self.data_index : self.data_index + AES_BLOCK_SIZE])
            self.data_index += AES_BLOCK_SIZE
            if self.data_index >= self.data_size:
                # Finished
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
        elif self.state == ReceiveState.SEND_ENC_REPLY_HEADER_WITH_CALLBACK2:
            # Encrypted stage. Send reply header to the client (callback2 pending).
            self.output_block = self.encrypt.encrypt(self.reply_header)
            self.state = ReceiveState.EXECUTE_CALLBACK2
        elif self.state == ReceiveState.EXECUTE_CALLBACK2:
            # Execute callback2 handler when header has been sent (nothing should be sent).
            pass
        elif self.state == ReceiveState.DISCONNECT:
            pass

    def handle_enc_request_end(self) -> None:
        """Process the end of an encrypted request,
        i.e. verify integrity, call a handler, prepare to send reply data."""

        # Check data hash is correct
        request_data_size = self.data_size
        expect_hash = self.generate_enc_data_hash(self.request_header, self.data[:request_data_size])
        if expect_hash != self.request_header[HEADER_DATA_HASH_OFFSET:]:
            self.state = ReceiveState.SEND_CORRUPT_ERROR
            return

        # Process the request, getting new data and parameter
        (_, parameter, msg_type, _) = __unpack_header(self.request_header)

        # Check handler is valid (this was already checked, but g_handler_table may have changed)
        handler_id = msg_type - ID_FIRST_HANDLER
        if handler_id not in g_handler_table:
            self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
            if DEBUG_HANDLERS:
                print("BadHandlerError: {} not in table at end".format(handler_id))
            return

        # Default to send to callback2 if callback1 is not set
        reply_data_size = request_data_size
        result = parameter

        handler = g_handler_table[handler_id]
        if handler.callback1:
            # call first handler
            if DEBUG_HANDLERS:
                print("Calling [{}].callback1 with {}".format(msg_type, (self.data[:request_data_size], parameter)))
            try:
                # Call parameters: (msg_type, data_buffer, input_data_size, input_parameter, arg)
                # Return value: (reply_data_size, return_value)
                return_value = handler.callback1(msg_type, self.data, request_data_size, parameter, handler.arg)
            except Exception as e:
                self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
                if DEBUG_HANDLERS:
                    print("BadHandlerError: callback1 exception {}".format(e))
                return
            if DEBUG_HANDLERS:
                print("Result [{}].callback1 with return {}".format(msg_type, return_value))

            # expect return value: (reply_data_size, return_value)
            if ((type(return_value) != tuple)
            or (len(return_value) != 2)
            or (type(return_value[0]) != int)
            or (type(return_value[1]) != int)):
                self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
                if DEBUG_HANDLERS:
                    print("BadHandlerError: callback1 unexpected return type {}".format(return_value))
                return
            (reply_data_size, result) = return_value

            # Limit data size as the C implementation does
            reply_data_size = min(MAX_DATA_SIZE, max(0, reply_data_size))
            self.data_size = reply_data_size

        self.data_index = 0

        if g_handler_table[handler_id].callback2:
            # prepare to call the second handler; no data will be sent via the network,
            # but it will be available for callback2. The request header is repacked with
            # new information to be used by callback2.
            self.request_header = __pack_header(reply_data_size, result, msg_type)
            self.state = ReceiveState.SEND_ENC_REPLY_HEADER_WITH_CALLBACK2
            reply_data_size = 0
        else:
            # no second handler, return data
            self.state = ReceiveState.SEND_ENC_REPLY_HEADER

        # Generate reply header
        self.output_header = __pack_header(reply_data_size, result, ID_OK,
            self.generate_enc_data_hash(__pack_header(reply_data_size, result, ID_OK),
                                        self.data[:reply_data_size]))

    def handle_enc_request_start(self) -> None:
        """Process the start of an encrypted request,
        i.e. check the header and start the input data transfer."""
        # Decrypt 
        self.request_header = self.decrypt.decrypt(self.input_block[:AES_BLOCK_SIZE])

        # Check handler ID is within the allowed range
        (data_size, parameter, msg_type, _) = __unpack_header(self.request_header)
        handler_id = msg_type - ID_FIRST_HANDLER
        if handler_id not in g_handler_table:
            self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
            if DEBUG_HANDLERS:
                print("BadHandlerError: {} not in table".format(handler_id))
            return
        if not (g_handler_table[handler_id].callback1
                or g_handler_table[handler_id].callback2):
            self.state = ReceiveState.SEND_BAD_HANDLER_ERROR
            if DEBUG_HANDLERS:
                print("BadHandlerError: {} lacks any callback".format(handler_id))
            return

        # Check parameters are valid, start processing the request
        if data_size > MAX_DATA_SIZE:
            self.state = ReceiveState.SEND_BAD_PARAM_ERROR
            return

        # Prepare for receiving the request payload
        self.data_size = data_size
        if data_size == 0:
            # There is no payload - go direct to the end
            self.handle_enc_request_end()
        else:
            # Payload needed
            self.state = ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD

    def handle_enc_request_add_data(self) -> None:
        """Process data input for an encrypted request."""
        self.data += self.decrypt.decrypt(self.input_block[:AES_BLOCK_SIZE])
        if len(self.data) >= self.data_size:
            # No more blocks
            self.handle_enc_request_end()

    def handle_input_block(self) -> bool:
        """Handle the input appropriately for the current state."""
        if self.state == ReceiveState.SEND_GREETING:
            # First message, server to client. Say hello.
            return False
        elif self.state == ReceiveState.EXPECT_REQUEST:
            # Second message, client to server. Client sends the client challenge.
            if self.input_block[0] != ID_REQUEST:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            elif not g_secret_valid:
                self.state = ReceiveState.SEND_NO_SECRET_ERROR
            else:
                self.client_challenge = self.input_block[1:AES_BLOCK_SIZE]
                self.state = ReceiveState.SEND_CHALLENGE
            return True
        elif self.state == ReceiveState.SEND_CHALLENGE:
            # Third message, server to client. Server sends the server challenge.
            return False
        elif self.state == ReceiveState.EXPECT_AUTHENTICATION:
            # Fourth message, client to server. Client sends the client authentication.
            if self.input_block[0] != ID_AUTHENTICATION:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            else:
                check_authentication = self.generate_authentication(b"CA")[:CHALLENGE_SIZE]
                if check_authentication != self.input_block[1:]:
                    self.state = ReceiveState.SEND_AUTH_ERROR
                else:
                    self.state = ReceiveState.SEND_AUTHENTICATION
            return True
        elif self.state == ReceiveState.SEND_AUTHENTICATION:
            # Fifth message, server to client. Server sends the server authentication.
            return False
        elif self.state == ReceiveState.EXPECT_ACKNOWLEDGE:
            # Sixth message, client to server. Client indicates authentication is complete.
            if self.input_block[0] != ID_ACKNOWLEDGE:
                self.state = ReceiveState.SEND_BAD_MSG_ERROR
            else:
                self.state = ReceiveState.EXPECT_ENC_REQUEST_HEADER
                # Session keys can be generated now
                self.generate_keys()
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
            self.handle_enc_request_start()
            return True
        elif self.state == ReceiveState.EXECUTE_CALLBACK2:
            # Execute callback2 handler when header has been sent (nothing should be received).
            return False
        elif self.state == ReceiveState.EXPECT_ENC_REQUEST_PAYLOAD:
            # Encrypted stage. Awaiting payload data from the client.
            self.handle_enc_request_add_data()
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

    def send_while_able(self, sock: socket.socket) -> None:
        """Send as many output blocks as possible now. This is limited by LwIP's
        buffers as well as the receiving side."""
        while True:
            # check if an output block is waiting to be sent
            if len(self.output_block) == 0:
                # try to generate an output block
                self.generate_output_block()
                if len(self.output_block) == 0:
                    # There is nothing to send
                    return

            # try to send a block - we can't tell if this will succeed beforehand
            try:
                size = sock.send(self.output_block)
            except Exception:
                # failure, some unhandlable error - abandon the connection
                self.state = ReceiveState.DISCONNECT
                return

            if size != len(self.output_block):
                # failure, block is not completely sent, we
                # should try again later, after some data has been sent
                self.output_block = self.output_block[size:]
                return

            # success, block has been sent - generate another if possible
            self.output_block = b""

    def server_socket_callback(self, sock: socket.socket) -> None:
        """Receive and send as many blocks as possible."""

        input_buffer_overflow = False
        try:
            self.input_block += sock.recv(AES_BLOCK_SIZE * 100)
        except Exception:
            # failure, some unhandlable error - abandon the connection
            self.state = ReceiveState.DISCONNECT
            self.input_block = b""

        while len(self.input_block) >= AES_BLOCK_SIZE:
            # Process the block
            if not self.handle_input_block():
                # Unable to handle input right now!
                # (There is no buffer space for this.)
                # We will disconnect, possibly after sending an error message
                input_buffer_overflow = True
                break
            self.input_block = self.input_block[AES_BLOCK_SIZE:]

        # disconnect before sending anything if requested by handle_input_block
        if self.state == ReceiveState.DISCONNECT:
            try:
                sock.close()
            except Exception:
                pass
            return

        # Send data (if any)
        # send_while_able may also enter the DISCONNECT state
        self.send_while_able(sock)

        # disconnect after sending anything if requested by send_while_able
        # or if there was an overflow while receiving
        if (self.state == ReceiveState.DISCONNECT) or input_buffer_overflow:
            self.state = ReceiveState.DISCONNECT
            try:
                sock.close()
            except Exception:
                pass
            return

        # Special case for executing a callback after closing the connection
        # This may not work as there is no callback for tcp_sent
        if self.state == ReceiveState.EXECUTE_CALLBACK2:
            # Data has been sent, execute callback2 if it exists (close first)
            self.state = ReceiveState.DISCONNECT
            try:
                sock.close()
            except Exception:
                return

            # Load the result from running callback1
            (_, result, msg_type, _) = __unpack_header(self.request_header)
            output_data_size = self.data_size
            handler_id = msg_type - ID_FIRST_HANDLER

            if handler_id in g_handler_table:
                handler = g_handler_table[handler_id]
                if handler.callback2:
                    if DEBUG_HANDLERS:
                        print("Calling [{}].callback2 with {}".format(msg_type, (self.data[:output_data_size], result)))
                    try:
                        # Call parameters: (msg_type, data_buffer, output_data_size, return_value, arg)
                        # Return value: None
                        handler.callback2(msg_type, self.data, output_data_size, result, handler.arg)
                    except Exception as e:
                        if DEBUG_HANDLERS:
                            print("BadHandlerError: callback2 exception {}".format(e))

            # Result of executing callback2 cannot be reported

def __set_micropython_lwip_callback(sock, callback):
    """Internal: register a function which will be called whenever
    tcp_recv or tcp_accept is called for the provided socket.

    mypy should ignore this function as setsockopt does not match the usual
    CPython library definition.

    The magic number 20 is from Micropython extmod/modlwip.c."""
    return sock.setsockopt(0, 20, callback)

def __server_accept(listen_sock: socket.socket) -> None:
    """Internal. A callback for a new connection (on the listening socket).

    A Session object is created for the new connection."""

    try:
        (client_sock, _) = listen_sock.accept()
    except Exception:
        return

    session = Session()
    __set_micropython_lwip_callback(client_sock, session.server_socket_callback)
    session.send_while_able(client_sock)

def __responder_recv(udp_sock: socket.socket) -> None:
    """Internal. This callback is called when a UDP packet is received on the responder socket."""
    try:
        (packet, addr) = udp_sock.recvfrom(RESPONDER_MAX_SIZE)
    except Exception:
        return

    # Check magic
    if not packet.startswith(RESPONDER_REQUEST_MAGIC):
        # Invalid request - not magic
        return

    # Check board ID
    if not g_responder_reply_bytes[4:].startswith(packet[4:]):
        # Request is for a different board
        return

    # Respond to request with complete board id
    try:
        udp_sock.sendto(g_responder_reply_bytes, addr)
    except Exception:
        return

def set_handler(
        msg_type: int,
        callback1: remote_handlers.HandlerCallback1,
        arg: typing.Any) -> None:
    """Register a stage 1 callback function to handle remote messages of the specified type.

    The handler is called when a request is received with a msg_type previously registered with
    wifi_settings_remote_set_handler.

    The user sends a (network) message containing a msg_type, some data (perhaps 0 bytes)
    and a parameter (int32_t) - all of these are received, decrypted (AES-256),
    and integrity checked (SHA-256) before the handler is invoked with the
    following parameters:
        (msg_type, data_buffer, input_data_size, input_parameter, arg)
    where
        msg_type identifies the handler and must be in range ID_FIRST_USER_HANDLER to
            ID_LAST_USER_HANDLER inclusive, matching the first parameter of set_handler
        data_buffer is a bytearray() buffer of size MAX_DATA_SIZE
            containing data received from the client (e.g. remote_picotool)
        input_data_size is the number of bytes in data_buffer which are valid for input,
            i.e. a value in range 0 to MAX_DATA_SIZE inclusive
        input_parameter is a 32-bit signed integer value received from the client
        arg is the third parameter of set_handler

    The callback function can make changes to data_buffer in order to reply with data.
    It should return a tuple:
        (output_data_size, return_value)
    where
        output_data_size is the number of bytes in data_buffer which are valid for output,
            i.e. a value in range 0 to MAX_DATA_SIZE inclusive
        return_value is a 32-bit signed integer value to be sent to the client
    """
    set_two_stage_handler(msg_type, callback1, None, arg)


def set_two_stage_handler(
        msg_type: int,
        callback1: remote_handlers.HandlerCallback1,
        callback2: remote_handlers.HandlerCallback2,
        arg: typing.Any) -> None:
    """Register stage 1 and stage2 callback functions to handle remote messages of the specified type.

    See set_handler for a description of callback1.
    
    After callback1 returns, the return value from callback1 is sent to the
    client but no data is sent. The connection is then closed, and callback2
    is called with the following parameters:
        (msg_type, data_buffer, output_data_size, return_value, arg)
    where
        msg_type identifies the handler and must be in range ID_FIRST_USER_HANDLER to
            ID_LAST_USER_HANDLER inclusive, matching the first parameter of set_two_stage_handler
        output_data_size is the first value returned by callback1; it is the number of bytes
            in data_buffer which are valid
        return_value is the second value returned by callback1 (this value has also been sent to the client)
        arg is the fourth parameter of set_two_stage_handler

    This second handler cannot return a value or any data. The purpose of two-part
    handlers is to support requests that put the Pico offline (e.g. reboot) as these
    have to be acknowledged before they are executed. Usually the first part will be
    used for validation, returning a non-zero value if validation fails, and then the second
    part will check the return_value from the first, and proceed
    only if validation was ok.

    msg_type identifies the handler and must be in range ID_FIRST_USER_HANDLER ..
    ID_LAST_USER_HANDLER inclusive.
    """
    handler_id = msg_type - ID_FIRST_HANDLER

    if ((handler_id >= NUM_HANDLERS) or (handler_id < 0)):
        raise IndexError(handler_id)

    g_handler_table[handler_id] = HandlerCallbackArg(callback1, callback2, arg)

def update_secret() -> None:
    """Re-read the wifi_settings file in Flash to obtain update_secret,
    this should be called if the secret is updated in memory so that the new
    value is used. (Note, this is called by init()).
    """
    global g_secret_valid, g_hmac_padded_key_1, g_hmac_padded_key_2
    g_secret_valid = False

    update_secret = storage.get_value_for_key("update_secret")
    if not update_secret:
        return

    secret_hashed = b"\x00" * HMAC_DIGEST_SIZE
    secret_bytes = update_secret.encode()
    for _ in range(4096):
        h1 = hashlib.sha256()
        h1.update(secret_hashed)
        h1.update(secret_bytes)
        secret_hashed = h1.digest()

    g_hmac_padded_key_1 = (bytes([k ^ 0x36 for k in secret_hashed])
            + bytes([0x36 for _ in range(HMAC_BLOCK_SIZE - HMAC_DIGEST_SIZE)]))
    g_hmac_padded_key_2 = (bytes([k ^ 0x5c for k in secret_hashed])
            + bytes([0x5c for _ in range(HMAC_BLOCK_SIZE - HMAC_DIGEST_SIZE)]))
    g_secret_valid = True

def __make_greetings() -> None:
    """Create greetings to be sent over the network to clients."""

    global g_remote_service_greeting, g_responder_reply_bytes

    # TCP greeting
    data = "xxx\r{}\rmicropython pico-wifi-settings version {}\r\n".format(
        hostname.get_board_id_hex(),
        configuration.WIFI_SETTINGS_VERSION_STRING).encode()
    # pad to block size
    data += (b"\x00" * (AES_BLOCK_SIZE - (len(data) % AES_BLOCK_SIZE)))

    # bytes 0 .. 2 are fixed fields in the reply
    # bytes 4 .. 19 contain the board ID in uppercase hex format
    # bytes 20 .. <unspecified> contain UTF-8 text that can be printed
    # Replace bytes 0 - 2
    data = bytes([ID_GREETING, PROTOCOL_VERSION, len(data) // AES_BLOCK_SIZE]) + data[3:]
    g_remote_service_greeting = data

    # Create a reply for sending via UDP (the responder) using the board ID
    g_responder_reply_bytes = RESPONDER_REPLY_MAGIC + data[4:4 + (BOARD_ID_SIZE * 2)]

def init() -> None:
    """Initialise the remote access service."""
    if g_remote_service_greeting:
        # Already initialised
        return

    # Load secret
    update_secret()

    # Create greetings to be sent over the network to clients
    __make_greetings()

    # Install basic handlers for messages
    set_handler(ID_PICO_INFO_HANDLER, remote_handlers.pico_info_handler, None)
    set_handler(ID_UPDATE_HANDLER, remote_handlers.update_handler, None)
    set_two_stage_handler(
            ID_UPDATE_REBOOT_HANDLER,
            remote_handlers.update_reboot_handler1,
            remote_handlers.update_reboot_handler2, None)

def listen(ip_address: str) -> None:
    """Bind TCP socket for remote service."""
    global g_remote_socket, g_responder_socket

    if g_remote_socket is not None:
        try:
            g_remote_socket.close()
        except Exception:
            pass
        g_remote_socket = None

    if g_responder_socket is not None:
        try:
            g_responder_socket.close()
        except Exception:
            pass
        g_responder_socket = None

    try:
        g_remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        g_remote_socket.bind((ip_address, PORT_NUMBER))
        g_remote_socket.listen(1)
        __set_micropython_lwip_callback(g_remote_socket, __server_accept)
    except Exception as e:
        print("wifi_settings.remote.listen: remote_socket: {}".format(e))

    try:
        # This won't work because of https://github.com/micropython/micropython/issues/3594
        g_responder_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        g_responder_socket.bind((ip_address, PORT_NUMBER))
        __set_micropython_lwip_callback(g_responder_socket, __responder_recv)
    except Exception as e:
        print("wifi_settings.remote.listen: responder_socket: {}".format(e))
