"""
Implementation of pico-wifi-settings client for use with Python asyncio.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .handler_ids import *
from .exceptions import *
from .version import PROTOCOL_VERSION
from .aes import AES256CBCFactory
from .asyncio_abstract_communication import AsyncioAbstractCommunication

import asyncio 
import struct
import typing

class Client(AsyncioAbstractCommunication):
    """Communications class for client side.

    The public interface of this class is the "run" method - other methods should not be called.
    """

    async def greeting(self) -> None:
        """First message, server to client. Say hello."""
        block = await self.read_block()
        (msg_type, version, num_blocks) = struct.unpack("<BBB", block[:3])
        if msg_type != ID_GREETING:
            raise BadMessageError(msg_type, ID_GREETING)
        if version != PROTOCOL_VERSION:
            raise BadVersionError(version)
        if num_blocks == 0:
            raise BadMessageError(msg_type, ID_GREETING)
        for i in range(num_blocks - 1):
            await self.read_block()

    async def request(self) -> bytes:
        """Second message, client to server. Client sends the client challenge."""
        client_challenge = os.urandom(CHALLENGE_SIZE)
        await self.write_block(struct.pack("<B", ID_REQUEST) + client_challenge)
        return client_challenge

    async def challenge(self) -> bytes:
        """Third message, server to client. Server sends the server challenge."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != ID_CHALLENGE:
            if msg_type == ID_NO_SECRET_ERROR:
                raise NoSecretError("Connection ok, but update_secret is not set on the server")
            raise BadMessageError(msg_type, ID_CHALLENGE)
        server_challenge = block[1:]
        return server_challenge

    async def authentication(self, client_authentication: bytes) -> None:
        """Fourth message, client to server. Client sends the client authentication."""
        await self.write_block(struct.pack("<B", ID_AUTHENTICATION) + client_authentication)

    async def response(self, server_authentication: bytes) -> None:
        """Fifth message, server to client. Server sends the server authentication."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != ID_RESPONSE:
            raise BadMessageError(msg_type, ID_RESPONSE)
        if server_authentication != block[1:]:
            raise AuthenticationError()

    async def acknowledge(self) -> None:
        """Sixth message, client to server. Client indicates authentication is complete."""
        await self.write_block(struct.pack("<B", ID_ACKNOWLEDGE) + PAD_BLOCK_1)

    def setup_aes(self, client_challenge: bytes, server_challenge: bytes) -> None:
        """Generate AES keys for client."""
        self.enc_receive = AES256CBCFactory(self.get_s2c_key(client_challenge, server_challenge))
        self.enc_transmit = AES256CBCFactory(self.get_c2s_key(client_challenge, server_challenge))

    def validate(self, msg_type: int, data_size: int, parameter: int) -> None:
        """Raise an exception if the request is invalid."""
        # Validation is on the other side
        pass

    async def run(self, handler_id: int, request_data: typing.Union[bytes, bytearray] = b"",
                  parameter: int = 0) -> typing.Tuple[bytes, int]:
        """Make a remote request.

        The client will negotiate an encryption key with the server if this has not already
        been done by an earlier call to "run".

        Then, it will send a request to execute the specified handler (based on handler_id)
        with the given parameter and request_data. The request will either result in
        an exception or a tuple of (result_data, result_value).
        """
        assert handler_id >= ID_FIRST_HANDLER
        assert handler_id <= 0xff

        try:
            if self.enc_receive is None:
                await self.setup()
            await self.transmit(handler_id, request_data, parameter)
            (msg_type, result_data, result_value) = await self.receive()

        except asyncio.IncompleteReadError:
            raise ConnectionError() from None
        except ConnectionResetError:
            raise ConnectionError() from None

        if msg_type == ID_OK:
            return (result_data, result_value)
        elif msg_type == ID_CORRUPT_ERROR:
            raise CorruptedMessageError("ID_CORRUPT_ERROR received")
        elif msg_type == ID_BAD_HANDLER_ERROR:
            raise BadHandlerError()
        elif msg_type == ID_BAD_PARAM_ERROR:
            raise BadParameterError()
        else:
            raise UnknownError()
