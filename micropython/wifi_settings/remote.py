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
import enum
import hashlib
import hmac
import os
import re
import struct
import socket
import sys
import traceback
import typing
from asyncio import StreamReader, StreamWriter
from pathlib import Path
from abc import abstractmethod

PORT_NUMBER =               1404
RESPONDER_REQUEST_MAGIC =  b"PWS?"
RESPONDER_REPLY_MAGIC =    b"PWS:"
BOARD_ID_SIZE =             8 

CHALLENGE_SIZE =            15
AUTHENTICATION_SIZE =       15
AES_BLOCK_SIZE =            16
DATA_HASH_SIZE =            7

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

PICO_ERROR_NOT_PERMITTED = -4
MAX_WIFI_SETTINGS_FILE_SIZE = 4096

# structures for ID_READ_HANDLER
# struct wifi_settings_logical_range_t {
#    void* start_address;
#    uint32_t size;
# };
# struct read_parameter_t {
#    wifi_settings_logical_range_t copy_from;
# };
READ_PARAMETER = struct.Struct("<II")

# structures for ID_OTA_FIRMWARE_UPDATE_HANDLER:
# #define WIFI_SETTINGS_OTA_HASH_SIZE 32
# struct wifi_settings_flash_range_t {
#    uint32_t start_address;
#    uint32_t size;
# };
# typedef struct ota_firmware_update_parameter_t {
#     wifi_settings_flash_range_t copy_from;
#     wifi_settings_flash_range_t copy_to;
#     uint8_t hash[WIFI_SETTINGS_OTA_HASH_SIZE];
# } ota_firmware_update_parameter_t;
OTA_FIRMWARE_UPDATE_PARAMETER = struct.Struct("<IIII")

PROTOCOL_VERSION = 1
AES_IV = b"\x00" * AES_BLOCK_SIZE
PAD_BLOCK_1 = b"\x00" * (AES_BLOCK_SIZE - 1)

FlashRange = typing.Tuple[int, int]

try:
    import pyaes # type: ignore
except ImportError:
    print("The pyaes module is required; please install it with 'pip install pyaes' or 'apt install python3-pyaes'")
    sys.exit(1)


def get_pad_bytes(data_size: int, block_size: int, pad_byte = b"\x00") -> bytes:
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
        self.enc_receive: typing.Optional[pyaes.aes.AESModeOfOperationCBC] = None
        self.enc_transmit: typing.Optional[pyaes.aes.AESModeOfOperationCBC] = None

    def gen_auth(self, session_data: bytes) -> bytes:
        """Generate authentication code from secret and session data."""
        return hmac.HMAC(key=self.update_secret_hash, msg=session_data,
                    digestmod=hashlib.sha256).digest()

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
        request_data += get_pad_bytes(len(request_data), AES_BLOCK_SIZE)

        # Add data
        num_blocks = len(request_data) // AES_BLOCK_SIZE
        for i in range(num_blocks):
            clear_block = request_data[i * AES_BLOCK_SIZE : (i + 1) * AES_BLOCK_SIZE]
            blocks.append(self.enc_transmit.encrypt(clear_block))

        # Send
        await self.write_block(b"".join(blocks))
