#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Integration tests for remote_picotool, including a server implementation
#

import argparse
import asyncio
import os
import pyaes  # type: ignore
import struct
import subprocess
import sys
import tempfile
import traceback
import typing
from pathlib import Path
from asyncio import StreamReader, StreamWriter
import pytest
import re

import remote_picotool

GREETING = b"\rpico-wifi-settings\r\n"
UPDATE_SECRET = "OWL001"
SERVER_ADDRESS = "localhost"

TEST_PATH = Path(__file__).parent.absolute()
PICO_WIFI_SETTINGS_ROOT_PATH = TEST_PATH.parent.parent.absolute()
REMOTE_PICOTOOL = PICO_WIFI_SETTINGS_ROOT_PATH / "remote_picotool"

# Test file 1 contains 2 blocks, intended to be loaded at logical addresses
# 0x10003100 and 0x10003200
TEST1_FILE_START_EXPECTED_DATA = b"\x00\xb5\xad\xf6"
TEST1_FILE_END_EXPECTED_DATA = b"\xba\x6a\xa2\x42"
TEST1_FILE_PATH = TEST_PATH / "data" / "test1.uf2"
TEST1_FILE_FAMILY = remote_picotool.Family.RP2350_ARM_S

# Test file 2 contains 2 blocks, the first is a workaround for RP2350-E10,
# the second is intended to be loaded at logical address 0x10000000
TEST2_FILE_PATH = TEST_PATH / "data" / "test2.uf2"
TEST2_FILE_FAMILY = remote_picotool.Family.RP2350_ARM_S

# Test file 3 contains blocks from the beginning and end of a real program,
# the final block ends at Flash location 0x5b100.
TEST3_FILE_PATH = TEST_PATH / "data" / "test3.uf2"
TEST3_FILE_FAMILY = remote_picotool.Family.RP2350_ARM_S

# Raw PicoInfo fields for a Pico 2 W with a program of size 0x1000 already in Flash
BASIC_PICO_INFO = """
flash_sector_size=0x1000
max_data_size=0x1000
sysinfo_chip_id=0x20004927
logical_offset=0x10000000
flash_all=0x00000000:0x00400000
flash_reusable=0x00001000:0x003fe000
flash_program=0x00000000:0x00001000
"""


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


class FakeRebootError(remote_picotool.RemoteError):
    """This is for the server mode."""
    pass

class Server(remote_picotool.AbstractCommunication):
    """Communications specialisation for server side."""

    def __init__(self,
            handlers: typing.Dict[int, HandlerCallback],
            update_secret: bytes,
            reader: StreamReader, writer: StreamWriter) -> None:
        remote_picotool.AbstractCommunication.__init__(self, update_secret, reader, writer)
        self.handlers = handlers

    async def greeting(self) -> None:
        """First message, server to client. Say hello."""
        data = struct.pack("<BBB", remote_picotool.ID_GREETING,
                        remote_picotool.PROTOCOL_VERSION, 0) + GREETING
        data += remote_picotool.get_pad_bytes(len(data), remote_picotool.AES_BLOCK_SIZE)
        num_blocks = len(data) // remote_picotool.AES_BLOCK_SIZE
        data = struct.pack("<BBB", remote_picotool.ID_GREETING,
                        remote_picotool.PROTOCOL_VERSION, num_blocks) + data[3:]
        await self.write_block(data)

    async def request(self) -> bytes:
        """Second message, client to server. Client sends the client challenge."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != remote_picotool.ID_REQUEST:
            raise remote_picotool.BadMessageError(msg_type, remote_picotool.ID_REQUEST)
        client_challenge = block[1:]
        return client_challenge

    async def challenge(self) -> bytes:
        """Third message, server to client. Server sends the server challenge."""
        server_challenge = os.urandom(remote_picotool.CHALLENGE_SIZE)
        await self.write_block(struct.pack("<B", remote_picotool.ID_CHALLENGE) + server_challenge)
        return server_challenge

    async def authentication(self, client_authentication: bytes) -> None:
        """Fourth message, client to server. Client sends the client authentication."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != remote_picotool.ID_AUTHENTICATION:
            raise remote_picotool.BadMessageError(msg_type, remote_picotool.ID_AUTHENTICATION)

        if client_authentication != block[1:]:
            raise remote_picotool.AuthenticationError()

    async def response(self, server_authentication: bytes) -> None:
        """Fifth message, server to client. Server sends the server authentication."""
        await self.write_block(struct.pack("<B", remote_picotool.ID_RESPONSE) + server_authentication)

    async def acknowledge(self) -> None:
        """Sixth message, client to server. Client indicates authentication is complete."""
        block = await self.read_block()
        msg_type = block[0]
        if msg_type != remote_picotool.ID_ACKNOWLEDGE:
            raise remote_picotool.BadMessageError(msg_type, remote_picotool.ID_ACKNOWLEDGE)

    def setup_aes(self, client_challenge: bytes, server_challenge: bytes) -> None:
        """Generate AES keys for server."""
        self.enc_receive = pyaes.aes.AESModeOfOperationCBC(key=self.get_c2s_key(
                client_challenge, server_challenge), iv=remote_picotool.AES_IV)
        self.enc_transmit = pyaes.aes.AESModeOfOperationCBC(key=self.get_s2c_key(
                client_challenge, server_challenge), iv=remote_picotool.AES_IV)

    def validate(self, msg_type: int, data_size: int, parameter: int) -> None:
        """Raise an exception if the request is invalid."""
        if msg_type < remote_picotool.ID_FIRST_HANDLER:
            raise remote_picotool.BadHandlerError()
        handler = self.handlers.get(msg_type, None)
        if handler is None:
            raise remote_picotool.BadHandlerError()

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
            msg_type = remote_picotool.ID_CORRUPT_ERROR
            try:
                (msg_type, request_data, parameter) = await self.receive()
                handler = self.handlers[msg_type]
                (result_data, result_value) = await handler.callback1(request_data, parameter)
                msg_type = remote_picotool.ID_OK
                if handler.two_stage_handler:
                    # No data is returned, all data is passed to callback2
                    result_data = b""

            except remote_picotool.CorruptedMessageError as e:
                msg_type = remote_picotool.ID_CORRUPT_ERROR
                raise
            except remote_picotool.BadHandlerError as e:
                msg_type = remote_picotool.ID_BAD_HANDLER_ERROR
                raise
            except remote_picotool.BadParameterError as e:
                msg_type = remote_picotool.ID_BAD_PARAM_ERROR
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
                msg_type = remote_picotool.ID_UNKNOWN_ERROR
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

async def create_server(handlers: typing.Dict[int, HandlerCallback]) -> typing.Tuple[asyncio.base_events.Server, int]:
    server: typing.List[asyncio.Server] = []
    config = remote_picotool.RemotePicotoolCfg(argparse.Namespace())
    config.set("update_secret", UPDATE_SECRET)
    update_secret_hash = config.update_secret_hash

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

class PicoInfoHandler(HandlerCallback):
    def __init__(self, contents: str) -> None:
        self.contents = contents

    async def callback1(self, data: bytes, parameter: int) -> typing.Tuple[bytes, int]:
        assert len(data) == 0
        assert parameter == 0
        result_data = self.contents.encode("utf-8")
        return (result_data, len(result_data))

class WriteHandler(HandlerCallback):
    def __init__(self, writes: typing.List[typing.Tuple[int, bytes]]) -> None:
        self.writes = writes

    async def callback1(self, data: bytes, parameter: int) -> typing.Tuple[bytes, int]:
        self.writes.append((parameter, data))
        return (b"", 0)

class ReadHandler(HandlerCallback):
    async def callback1(self, data: bytes, parameter: int) -> typing.Tuple[bytes, int]:
        assert len(data) == 8
        assert parameter == 0
        (_, size) = struct.unpack("<II", data)
        assert size >= 8
        data += b"\x01" * (size - 9)
        data += b"\x02"
        return (data, 0)

class OTAHandler(HandlerCallback):
    two_stage_handler = True

    def __init__(self, ota_calls: typing.List[bytes]) -> None:
        self.ota_calls: typing.List[bytes] = ota_calls

    async def callback1(self, data: bytes, parameter: int) -> typing.Tuple[bytes, int]:
        assert parameter == 0
        self.ota_calls.append(data)
        return (b"", 0)

    async def callback2(self, callback1_data: bytes, callback1_result: int) -> None:
        assert callback1_result == 0
        self.ota_calls.append(callback1_data)

@pytest.mark.asyncio
async def test_info() -> None:
    # GIVEN
    # Test server that replies to info requests with a hostname 'hello'
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler("name=hello"),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the info command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "info", "--raw",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Correct info response containing the hostname, no errors
    assert 0 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^name=hello$", stdout, flags=re.MULTILINE)
    assert re.search(r"^\s*hostname:\s+hello$", stdout, flags=re.MULTILINE)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_wrong_password() -> None:
    # GIVEN
    # Test server with a default password
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler(""),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the info command, but a wrong password
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", "WRONG-PASSWORD", "--address", SERVER_ADDRESS,
            "--port", str(port),
            "info", "--raw",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Client program prints an error response explaining the problem
    # (An exception will also be printed by the server)
    assert 1 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^.*AuthenticationError.*--secret does not match the update_secret.*$",
            stdout, flags=re.MULTILINE)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_unsupported_command() -> None:
    # GIVEN
    # Test server that supports no handlers
    handlers: typing.Dict[int, HandlerCallback] = {}
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the info command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "info", "--raw",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Client program prints an error response explaining the problem
    # (An exception will also be printed by the server)
    assert 1 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^.*Remote error: BadHandlerError.*$",
            stdout, flags=re.MULTILINE)
    server.close()
    await server.wait_closed()

def test_get_file_type() -> None:
    # GIVEN
    # UF2 file
    # WHEN
    # get_file_type is called
    # THEN
    # result is UF2
    assert remote_picotool.get_file_type(TEST1_FILE_PATH) == remote_picotool.FileType.UF2

def test_uf2_reader() -> None:
    # GIVEN
    # UF2 reader: file containing some blocks for Pico 2 W, and a FileReader object
    pico_info = remote_picotool.PicoInfo(BASIC_PICO_INFO.encode("utf-8"))
    reader = remote_picotool.UF2FileReader(pico_info, TEST1_FILE_FAMILY)

    # WHEN
    # The file is read
    reader.read(TEST1_FILE_PATH)

    # THEN
    # Correct capture of the blocks and the start/end offset
    assert reader.size == 0x200
    assert reader.upper_bound == 0x3300
    assert reader.lower_bound == 0x3100
    assert reader.data.startswith(TEST1_FILE_START_EXPECTED_DATA)
    assert reader.data.endswith(TEST1_FILE_END_EXPECTED_DATA)

def test_uf2_reader_with_align() -> None:
    # GIVEN
    # UF2 reader: the PicoInfo provides a sector size and logical offset
    # Override the sector size to 0x200
    pico_info = remote_picotool.PicoInfo(
        ("flash_sector_size=0x200\n" + BASIC_PICO_INFO).encode("utf-8"))
    reader = remote_picotool.UF2FileReader(pico_info, TEST1_FILE_FAMILY)

    # WHEN
    # The file is read
    reader.read(TEST1_FILE_PATH)

    # THEN
    # Alignment function called -> padding added, data stays at 0x100..0x300
    reader.align()
    assert reader.lower_bound == 0x3000
    assert reader.upper_bound == 0x3400
    assert reader.size == 0x400
    assert reader.data[:0x100] == (b"\xff" * 0x100)
    assert reader.data[0x100:].startswith(TEST1_FILE_START_EXPECTED_DATA)
    assert reader.data[:0x300].endswith(TEST1_FILE_END_EXPECTED_DATA)
    assert reader.data[0x300:] == (b"\xff" * 0x100)

def test_uf2_reader_wrong_family() -> None:
    # GIVEN
    # UF2 reader: wrong family selected
    pico_info = remote_picotool.PicoInfo(BASIC_PICO_INFO.encode("utf-8"))
    reader = remote_picotool.UF2FileReader(pico_info, remote_picotool.Family.RP2040)

    # WHEN
    # The file is read
    with pytest.raises(remote_picotool.LocalError) as e:
        reader.read(TEST1_FILE_PATH)

    # THEN
    # Unexpected family error is raised
    assert re.match(r"^.*doesn't contain any blocks with the expected family.*RP2040.*$", str(e.value))

def test_uf2_reader_skip_rp2350_e10_workaround() -> None:
    # GIVEN
    # UF2 reader given a file which begins with a workaround for RP2350-E10
    pico_info = remote_picotool.PicoInfo(BASIC_PICO_INFO.encode("utf-8"))
    reader = remote_picotool.UF2FileReader(pico_info, TEST2_FILE_FAMILY)

    # WHEN
    # The file is read
    reader.read(TEST2_FILE_PATH)

    # THEN
    # RP2350-E10 block is ignored (this happens implicitly because the family id is RPXXXX_ABSOLUTE)
    assert reader.lower_bound == 0x0
    assert reader.upper_bound == 0x100
    assert reader.size == 0x100

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        yield temp_dir

@pytest.mark.asyncio
async def test_load_binary(temp_dir) -> None:
    # GIVEN
    # Test server that allows remote updates; binary file containing test data (1 block)
    temp_file = temp_dir / "tmp.bin"
    test_data = b"TEST 12345 \xff\xee\xdd"
    temp_file.write_bytes(test_data)
    writes: typing.List[typing.Tuple[int, bytes]] = []
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler("""
flash_sector_size=0x100
flash_reusable=0x10000:0x20000
max_data_size=0x100
""" + BASIC_PICO_INFO),
        remote_picotool.ID_FLASH_WRITE_HANDLER: WriteHandler(writes),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the load command and a specific load offset
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "load", "--offset", "0x12345", str(temp_file),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data uploaded as expected, with proper alignment padding
    assert 0 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^.*Load ok, offset 0x0*12300.*$", stdout, flags=re.MULTILINE)
    assert len(writes) == 1
    (offset, data) = writes[0]
    assert offset == 0x12300        # aligned to one block
    assert len(data) == 0x100       # size is one block
    assert data.startswith(b"\xff\xff")
    assert data.endswith(b"\xff\xff")
    assert data[0x45:].startswith(test_data + b"\xff\xff")
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_load_uf2() -> None:
    # GIVEN
    # Test server that allows remote updates, UF2 file containing some blocks,
    # PicoInfo structure representing Pico 2
    writes: typing.List[typing.Tuple[int, bytes]] = []
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler("""
flash_sector_size=0x100
max_data_size=0x100
""" + BASIC_PICO_INFO),
        remote_picotool.ID_FLASH_WRITE_HANDLER: WriteHandler(writes),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the load command and a specific load offset
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "load", str(TEST1_FILE_PATH),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data from UF2 uploaded as expected
    stdout = stdout_bytes.decode("utf-8")
    print(stdout)
    assert len(stderr_bytes) == 0
    assert 0 == await client.wait()
    assert re.search(r"^.*Load ok, offset 0x0*3100.*$", stdout, flags=re.MULTILINE)
    assert len(writes) == 2
    # Check block 0
    (offset, data) = writes[0]
    assert offset == 0x3100     # aligned to one block
    assert len(data) == 0x100   # size is one block
    assert data.startswith(TEST1_FILE_START_EXPECTED_DATA)
    # Check block 1
    (offset, data) = writes[1]
    assert offset == 0x3200     # aligned to one block
    assert len(data) == 0x100   # size is one block
    assert data.endswith(TEST1_FILE_END_EXPECTED_DATA)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_load_uf2_padding() -> None:
    # GIVEN
    # Test server that allows remote updates, UF2 file containing some blocks,
    # typical PicoInfo structure for Pico 2 W
    writes: typing.List[typing.Tuple[int, bytes]] = []
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler(BASIC_PICO_INFO),
        remote_picotool.ID_FLASH_WRITE_HANDLER: WriteHandler(writes),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the load command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "load", str(TEST1_FILE_PATH),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data from UF2 uploaded as expected
    stdout = stdout_bytes.decode("utf-8")
    print(stdout)
    assert len(stderr_bytes) == 0
    assert 0 == await client.wait()
    assert re.search(r"^.*Load ok, offset 0x0*3000.*$", stdout, flags=re.MULTILINE)
    assert len(writes) == 1
    (offset, data) = writes[0]
    assert offset == 0x3000     # aligned to one block
    assert len(data) == 0x1000  # size is one block
    # data should appear at offset 0x100 .. 0x300 in the block
    assert data.startswith(b"\xff" * 0x100)
    assert data[0x100:].startswith(TEST1_FILE_START_EXPECTED_DATA)
    assert data[:0x300].endswith(TEST1_FILE_END_EXPECTED_DATA)
    assert data.endswith(b"\xff" * 0xd00)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_ota() -> None:
    # GIVEN
    # Test server that allows remote updates, PicoInfo showing a
    # program of size 0x80000, followed by 0x60000 bytes of unused space,
    # UF2 file with a block range spanning 0x5b100 bytes. Max data size is
    # set to 64kb so that only 6 blocks are required.
    writes: typing.List[typing.Tuple[int, bytes]] = []
    ota_calls: typing.List[bytes] = []
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler("""
flash_reusable=0x80000:0xe0000
max_data_size=0x10000
""" + BASIC_PICO_INFO),
        remote_picotool.ID_FLASH_WRITE_HANDLER: WriteHandler(writes),
        remote_picotool.ID_OTA_FIRMWARE_UPDATE_HANDLER: OTAHandler(ota_calls),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the OTA command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "ota", str(TEST3_FILE_PATH),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data from UF2 uploaded as expected
    stdout = stdout_bytes.decode("utf-8")
    print(stdout)
    assert len(stderr_bytes) == 0
    assert 0 == await client.wait()

    # Check the load operation - expect 6 blocks
    # starting at 0x80000, because this is the end of the current program
    assert len(writes) == 6
    for i in range(5):
        (offset, data) = writes[i]
        assert offset == (0x80000 + (i * 0x10000))
        assert len(data) == 0x10000
    i = 5
    (offset, data) = writes[i]
    assert offset == (0x80000 + (i * 0x10000))
    assert len(data) == 0xc000

    assert re.search(r"^.*Load ok, offset 0x0*80000.*$", stdout, flags=re.MULTILINE)

    # Check the ota operation - expect two calls, the first containing the copy information
    assert len(ota_calls) == 2
    data = ota_calls[0]
    assert len(data) == 48          # four 32-bit fields and one SHA-256
    copy_data = struct.unpack("<IIII", data[:16])
    assert copy_data[0] == 0x80000  # field 0: install from
    assert copy_data[1] == 0x5c000  # field 1: total size
    assert copy_data[2] == 0x0      # field 2: install to
    assert copy_data[3] == 0x5c000  # field 3: total size

    data = ota_calls[1]
    assert len(data) == 0           # callback2 was called, beginning installation

    assert re.search(r"^.*Verify ok.*accepted: 0x0*80000.*0x0*dc000.*0x0*0.*0x0*5c000.*$", stdout, flags=re.MULTILINE)

    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_without_enough_space() -> None:
    # GIVEN
    # Test server that allows remote updates, PicoInfo showing a
    # program of size 0x10000, followed by 0x70000 bytes of unused space,
    # UF2 file with a block range spanning 0x5b100 bytes. (Actually,
    # installation would be possible here, but it would require a copy
    # algorithm that erased the destination one block at a time, and this
    # feature would only be useful in cases where a large program replaces
    # a small one.)
    writes: typing.List[typing.Tuple[int, bytes]] = []
    ota_calls: typing.List[bytes] = []
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler("""
flash_reusable=0x10000:0x80000
""" + BASIC_PICO_INFO),
        remote_picotool.ID_FLASH_WRITE_HANDLER: WriteHandler(writes),
        remote_picotool.ID_OTA_FIRMWARE_UPDATE_HANDLER: OTAHandler(ota_calls),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the OTA command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "ota", str(TEST3_FILE_PATH),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data from UF2 can't be uploaded because there isn't enough space
    # to store both the temporary copy (at 0x5c000) and also the installed
    # version (at 0x0).
    assert 1 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^.*cannot be loaded.*written outside of.*0x0*5c000.*0x0*80000.*$", stdout, flags=re.MULTILINE)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_save(temp_dir) -> None:
    # GIVEN
    # Test server that allows remote updates, PicoInfo that sets a suitable block size
    temp_file = temp_dir / "tmp.bin"
    block_size = 0x1000
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler(
            f"max_data_size=0x{block_size:x}\n" + BASIC_PICO_INFO),
        remote_picotool.ID_READ_HANDLER: ReadHandler(),
    }
    num_blocks = 9
    start_address = 0x87654321
    final_block_size = 0x321
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the save command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "save", "--range",
            hex(start_address), hex(start_address + ((num_blocks - 1) * block_size) + final_block_size),
            str(temp_file),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Data saved from memory
    assert 0 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert temp_file.is_file()
    all_data = temp_file.read_bytes()
    assert len(all_data) == (((num_blocks - 1) * block_size) + final_block_size)

    for i in range(num_blocks):
        block_data = all_data[i * block_size : (i + 1) * block_size]
        (address, size) = struct.unpack("<II", block_data[:8])
        assert size == len(block_data)
        assert block_data[8:-1] == (b"\x01" * (len(block_data) - 9))
        assert block_data[-1:] == b"\x02"
        assert address == (start_address + (i * block_size))

    assert re.search(r"^Save ok.*$", stdout, flags=re.MULTILINE)
    server.close()
    await server.wait_closed()

@pytest.mark.asyncio
async def test_unsupported_memory_access(temp_dir) -> None:
    # GIVEN
    # Test server that does not allow remote memory accesses
    temp_file = temp_dir / "tmp.bin"
    handlers: typing.Dict[int, HandlerCallback] = {
        remote_picotool.ID_PICO_INFO_HANDLER: PicoInfoHandler(BASIC_PICO_INFO),
    }
    (server, port) = await create_server(handlers)

    # WHEN
    # Running the client program with the save command
    client = await asyncio.create_subprocess_exec(
            str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(port),
            "save", str(temp_file),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout_bytes, stderr_bytes) = await client.communicate()

    # THEN
    # Suitable error reported
    assert 1 == await client.wait()
    assert len(stderr_bytes) == 0
    stdout = stdout_bytes.decode("utf-8")
    assert re.search(r"^.*Remote error: .*firmware does not support the 'save' command and must be recompiled with memory access features.*$", stdout, flags=re.MULTILINE)

    server.close()
    await server.wait_closed()
