"""
Implementation of pico-wifi-settings server for use with Python asyncio.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..handler_ids import *
from ..exceptions import *
from ..version import PROTOCOL_VERSION
from ..aes import AES256CBCFactory, AES_BLOCK_SIZE
from .abstract_communication import AbstractCommunication
from ..protocol import CHALLENGE_SIZE, get_pad_bytes

from asyncio import StreamReader, StreamWriter

import asyncio 
import os
import struct
import typing

GREETING = b"\rpico-wifi-settings asyncio server\r\n"

class HandlerCallback:
    """Represents a handler for a remote request."""
    two_stage_handler = False

    async def callback1(self, input_data: bytes, input_parameter: int) -> typing.Tuple[bytes, int]:
        """Execute before sending reply data.

        If two_stage_handler = False then the function should return the output data and result value.
        If two_stage_handler = True then the function should return data for callback2 and result value.
        """
        return (input_data, input_parameter)

    async def callback2(self, callback1_data: bytes, callback1_result: int) -> None:
        """Execute after sending reply data, if two_stage_handler = True.

        This receives whatever data was returned by callback1."""
        pass

class Server(AbstractCommunication):
    """Communications class for server side.

    The public interface of this class is the "run" method:
    other methods should not be called. The intended use is:

        await remote_picotool.Server(handlers, update_secret_hash, reader, writer).run()

    The caller should supply all handlers including those
    for "built-in" features such as ID_PICO_INFO_HANDLER.
    """

    def __init__(self,
            handlers: typing.Dict[int, HandlerCallback],
            update_secret_hash: bytes,
            reader: StreamReader, writer: StreamWriter) -> None:
        """Create a new server instance.

        handlers should be a dictionary mapping a handler id to a handler
        callback object. Handler ids are in the range
        ID_FIRST_HANDLER .. ID_LAST_USER_HANDLER.

        The update secret should be a hash from the update_secret_hash
        function."""
        AbstractCommunication.__init__(self, update_secret_hash, reader, writer)
        self.handlers = handlers

    async def greeting(self) -> None:
        """First message, server to client. Say hello."""
        data = struct.pack("<BBB", ID_GREETING,
                        PROTOCOL_VERSION, 0) + GREETING
        data += get_pad_bytes(len(data))
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
        self.enc_receive = AES256CBCFactory(self.get_c2s_key(client_challenge, server_challenge))
        self.enc_transmit = AES256CBCFactory(self.get_s2c_key(client_challenge, server_challenge))

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
