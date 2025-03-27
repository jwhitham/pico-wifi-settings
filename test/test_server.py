#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Test server for remote_picotool
#

import argparse
import asyncio
import os
import pyaes  # type: ignore
import struct
import sys
import traceback
import typing
from asyncio import StreamReader, StreamWriter
from pathlib import Path

from remote_picotool import (
        ID_GREETING, ID_PICO_INFO_HANDLER, ID_REQUEST, ID_CHALLENGE,
        ID_AUTHENTICATION, ID_RESPONSE, ID_ACKNOWLEDGE, ID_FIRST_HANDLER,
        ID_CORRUPT_ERROR, ID_BAD_HANDLER_ERROR, ID_BAD_PARAM_ERROR,
        ID_UNKNOWN_ERROR, ID_UPDATE_REBOOT_HANDLER, ID_OK,
        PROTOCOL_VERSION, AES_BLOCK_SIZE, CHALLENGE_SIZE, AES_IV, PORT_NUMBER,
        RemoteError, BadMessageError, AuthenticationError, BadHandlerError,
        CorruptedMessageError, BadParameterError,
        AbstractCommunication,
        get_update_secret, get_pad_bytes)

GREETING = b"\rpico-wifi-settings\r\n"

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


class FakeRebootError(RemoteError):
    """This is for the server mode."""
    pass

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
        data = struct.pack("<BBB", ID_GREETING, PROTOCOL_VERSION, 0) + GREETING
        data += get_pad_bytes(len(data), AES_BLOCK_SIZE)
        num_blocks = len(data) // AES_BLOCK_SIZE
        data = struct.pack("<BBB", ID_GREETING, PROTOCOL_VERSION, num_blocks) + data[3:]
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
        self.enc_receive = pyaes.aes.AESModeOfOperationCBC(key=self.get_c2s_key(
                client_challenge, server_challenge), iv=AES_IV)
        self.enc_transmit = pyaes.aes.AESModeOfOperationCBC(key=self.get_s2c_key(
                client_challenge, server_challenge), iv=AES_IV)

    def validate(self, msg_type: int, data_size: int, parameter: int) -> None:
        """Raise an exception if the request is invalid."""
        if msg_type < ID_FIRST_HANDLER:
            raise BadHandlerError()
        handler = self.handlers.get(msg_type, None)
        if handler is None:
            raise BadHandlerError()

    async def run(self) -> None:
        """Run server."""
        await self.setup()

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
            except FakeRebootError:
                # Fake reboot event (probably from running a handler)
                raise
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
                try:
                    await handler.callback2(result_data, result_value)
                except FakeRebootError:
                    # Fake reboot in deferred handler
                    raise

def main() -> None:
    """This is a test mode that acts as a server."""
    args = argparse.Namespace()
    args.secret = "test1234"
    update_secret = get_update_secret(args)

    class FakePicoInfoHandler(HandlerCallback):
        async def callback1(self, data: bytes, parameter: int) -> typing.Tuple[bytes, int]:
            if (len(data) != 0) or (parameter != 0):
                return (b"", -1)

            result_data = b"name=hello"
            return (result_data, len(result_data))

    class FakeUpdateRebootHandler(HandlerCallback):
        two_stage_handler = True
        async def callback2(self, data: bytes, parameter: int) -> None:
            print(f"callback2 handler reboots! parameter = {parameter}", flush=True)
            raise FakeRebootError()


    handlers: typing.Dict[int, HandlerCallback] = {
        ID_PICO_INFO_HANDLER: FakePicoInfoHandler(),
        ID_UPDATE_REBOOT_HANDLER: FakeUpdateRebootHandler(),
    }

    server: typing.List[asyncio.Server] = []
    async def serve_callback(reader: StreamReader, writer: StreamWriter) -> None:
        try:
            await Server(handlers, update_secret, reader, writer).run()
        except FakeRebootError:
            server[0].close()
        except KeyboardInterrupt:
            server[0].close()
        except Exception as e:
            print(str(e))
            traceback.print_exc()
            server[0].close()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def run() -> None:
        server.append(await asyncio.start_server(serve_callback, "localhost", PORT_NUMBER))
        await server[0].start_serving()
        await server[0].wait_closed()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
