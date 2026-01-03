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
AES_IV = b"\x00" * AES_BLOCK_SIZE
PAD_BLOCK_1 = b"\x00" * (AES_BLOCK_SIZE - 1)

# CBC mode, see https://github.com/micropython/micropython/blob/master/docs/library/cryptolib.rst
CIPHER_MODE = 2

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

