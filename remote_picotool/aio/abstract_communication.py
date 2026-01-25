"""
Abstract implementation of pico-wifi-settings remote protocol for use with Python asyncio.

This can act either as a client or server. It implements the
sequence of actions needed to implement the protocol such as
negotiating a session key. It requires the Python asyncio module.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..handler_ids import *
from ..exceptions import *
from ..aes import AbstractAES256CBCFactory, AES_BLOCK_SIZE
from ..protocol import CHALLENGE_SIZE, AUTHENTICATION_SIZE
from ..protocol import DATA_HASH_SIZE, HEADER_SIZE, PAD_BLOCK_1
from ..protocol import get_pad_bytes

from abc import abstractmethod
from asyncio import StreamReader, StreamWriter

import asyncio 
import hashlib
import hmac
import struct
import typing

class AbstractCommunication:
    """Abstract implementation of pico-wifi-settings remote protocol for use with Python asyncio."""

    def __init__(self, update_secret_hash: bytes, reader: StreamReader, writer: StreamWriter) -> None:
        """Create new object implementing the pico-wifi-settings remote protocol."""
        self.reader = reader
        self.writer = writer
        self.update_secret_hash = update_secret_hash
        self.enc_receive: typing.Optional[AbstractAES256CBCFactory] = None
        self.enc_transmit: typing.Optional[AbstractAES256CBCFactory] = None

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

    async def transmit(self, msg_type: int, request_data: typing.Union[bytes, bytearray], parameter: int) -> None:
        """Transmit an encrypted message to the other side."""

        assert self.enc_transmit is not None
        if isinstance(request_data, bytearray):
            request_data = bytes(request_data)

        # Send header
        header = struct.pack("<IiB", len(request_data), parameter, msg_type)
        data_hash = self.get_data_hash(request_data, header)
        clear_block = header + data_hash
        assert len(clear_block) == AES_BLOCK_SIZE
        blocks = [self.enc_transmit.encrypt(clear_block)]

        # Pad data to block boundary
        request_data += get_pad_bytes(len(request_data))

        # Add data
        num_blocks = len(request_data) // AES_BLOCK_SIZE
        for i in range(num_blocks):
            clear_block = request_data[i * AES_BLOCK_SIZE : (i + 1) * AES_BLOCK_SIZE]
            blocks.append(self.enc_transmit.encrypt(clear_block))

        # Send
        await self.write_block(b"".join(blocks))
