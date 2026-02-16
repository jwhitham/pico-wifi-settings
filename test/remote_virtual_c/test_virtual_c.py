#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# mypy test
#

import asyncio
import pytest
import os
import subprocess
import sys
import tempfile
import typing
from pathlib import Path
import wifi_settings
from wifi_settings import remote_picotool

UPDATE_SECRET = "OWL001"
SERVER_ADDRESS = "127.0.0.1"

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.parent.absolute()
TEST_PATH = PICO_WIFI_SETTINGS_ROOT_PATH / "test" / "remote_virtual_c"
REMOTE_PICOTOOL = PICO_WIFI_SETTINGS_ROOT_PATH / "remote_picotool"

ID_TEST_HANDLER_ECHO_XOR_COUNT = (wifi_settings.ID_FIRST_USER_HANDLER + 0)
ID_TEST_HANDLER_GEN_OUTPUT     = (wifi_settings.ID_FIRST_USER_HANDLER + 1)
ID_TEST_HANDLER_BOUNDS_CHECK   = (wifi_settings.ID_FIRST_USER_HANDLER + 2)
INT_MIN = -0x80000000
INT_MAX = 0x7fffffff

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        yield temp_dir

class ServerHandle:
    def __init__(self, temp_dir):
        self.test_build_path = Path(temp_dir) / "build"
        self.test_run_path = Path(temp_dir)
        self.test_program = self.test_build_path / "remote_virtual"
        self.server_handle = None
        self.tcp_port = -1
        self.config = remote_picotool.BaseRemotePicotoolCfg()

    async def start(self) -> None:
        self.test_build_path.mkdir()
        print("cmake", flush=True)
        cmake_handle = await asyncio.create_subprocess_exec("cmake", "-DCMAKE_BUILD_TYPE=Debug", str(TEST_PATH),
            cwd=str(self.test_build_path))
        rc = await cmake_handle.wait()
        assert rc == 0
        print("make", flush=True)
        make_handle = await asyncio.create_subprocess_exec("make", cwd=str(self.test_build_path))
        rc = await make_handle.wait()
        assert rc == 0

        assert self.test_program.exists()

        # start server
        print("server", flush=True)
        self.server_handle = await asyncio.create_subprocess_exec(
                str(self.test_program), UPDATE_SECRET, cwd=str(self.test_run_path))

        # Wait for server start
        self.tcp_port = await self.read_port_file("tcp_listen_*")


        self.config.set("update_secret", UPDATE_SECRET)
        self.config.set("board_address", SERVER_ADDRESS)
        self.config.set("port", str(self.tcp_port))

    async def read_port_file(self, search: str) -> int:
        # Wait for port file to be created (telling us the server's port number)
        # Expecting a file named something like "tcp_listen_41234" where the final
        # characters are the 16-bit port number in decimal format.
        port = -1
        for attempt in range(100):
            for found in self.test_run_path.glob(search):
                suffix = found.name.rpartition("_")[2]
                print(found.name)
                try:
                    return int(suffix, 10)
                except Exception:
                    pass

            await asyncio.sleep(0.05)

        assert False, "server subprocess did not create port file " + search

@pytest.mark.asyncio
async def test_info(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()

    reader, writer = await remote_picotool.get_pico_connection(server_handle.config)
    client = remote_picotool.Client(server_handle.config.update_secret_hash, reader, writer)

    # Test - info dump
    (result_data, result_value) = await client.run(wifi_settings.ID_PICO_INFO_HANDLER)
    pico_info = wifi_settings.PicoInfo(result_data)
    assert pico_info.get_str("implementation") == "TestC"
    assert pico_info.board_id == "123456789ABCDEF0"
    assert pico_info.name == "test-host-name"
    assert pico_info.max_data_size >= 1024

async def connect(config: remote_picotool.BaseRemotePicotoolCfg) -> typing.Tuple[
                remote_picotool.Client, asyncio.StreamWriter, int]:
    # Make a new connection to the server and get the max_data_size
    reader, writer = await remote_picotool.get_pico_connection(config)
    client = remote_picotool.Client(config.update_secret_hash, reader, writer)
    (result_data, result_value) = await client.run(wifi_settings.ID_PICO_INFO_HANDLER)
    max_data_size = wifi_settings.PicoInfo(result_data).max_data_size
    return (client, writer, max_data_size)

@pytest.mark.asyncio
async def test_out_of_range_data(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, max_data_size) = await connect(server_handle.config)
    writer.close()
    await writer.wait_closed()

    # Test - out of range data sizes
    for size in [max_data_size + 1, -1, max_data_size + (1 << 32)]:
        reader, writer = await remote_picotool.get_pico_connection(server_handle.config)
        client = remote_picotool.Client(server_handle.config.update_secret_hash, reader, writer)
        try:
            print("out of range data size", size, " ", end="", flush=True)
            size = max_data_size + 1
            parameter = -size
            request_data = bytearray(size)
            (result_data, result_value) = await client.run(ID_TEST_HANDLER_ECHO_XOR_COUNT, request_data, parameter)
            raise Exception()
        except wifi_settings.BadParameterError:
            print("OK")

        writer.close()
        await writer.wait_closed()

@pytest.mark.asyncio
async def test_echo_xor_count(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, max_data_size) = await connect(server_handle.config)

    # Test - sending and receiving data of various sizes
    sizes = [16, 1, 15, 17, 0, 500, 511, 513, max_data_size, max_data_size - 1]
    for size in sizes:
        assert size <= max_data_size
        parameter = -size
        print("test_handler_echo_xor_count", size, parameter, flush=True)
        request_data = bytearray(os.urandom(size))
        expected_result_data = bytearray(size)
        expected_result = -10
        for i in range(size):
            if request_data[i] == 0x41:
                expected_result -= 1
            expected_result_data[i] = request_data[i] ^ 0xac

        print("sending", flush=True)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_ECHO_XOR_COUNT, request_data, parameter)
        print("checking", len(result_data), result_value)
        assert result_value == expected_result
        assert len(result_data) == size
        assert result_data == bytes(expected_result_data)
        print("OK", flush=True)

    writer.close()
    await writer.wait_closed()

@pytest.mark.asyncio
async def test_gen_output(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, max_data_size) = await connect(server_handle.config)

    # Test - receiving more data than was sent
    sizes = [16, 1, 15, 17, 0, 500, 511, 513, max_data_size, max_data_size - 1,
            -1, max_data_size + 1, INT_MIN, INT_MAX]
    for parameter in sizes:
        size = 0
        print("test_handler_gen_output", size, parameter, end="", flush=True)
        expected_result = parameter ^ 1
        request_data = bytearray(0)
        if parameter < 0:
            expected_result_data = bytearray(0)
        elif parameter < max_data_size:
            expected_result_data = bytearray(parameter)
        else:
            expected_result_data = bytearray(max_data_size)
        for i in range(len(expected_result_data)):
            expected_result_data[i] = (i + 1) & 0xff

        print(", sending", end="", flush=True)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_GEN_OUTPUT, request_data, parameter)
        print(", checking", len(result_data), result_value, end="")
        assert result_value == expected_result
        assert len(result_data) == len(expected_result_data)
        assert result_data == bytes(expected_result_data)
        print(", OK", flush=True)

    writer.close()
    await writer.wait_closed()

@pytest.mark.asyncio
async def test_bounds_check(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, max_data_size) = await connect(server_handle.config)

    # Test - edge cases for parameters and result values
    for (parameter, expected_result) in {
            INT_MIN: -1,
            INT_MAX: -2,
            0: -3,
            -1: INT_MIN,
            -2: INT_MAX,
            -3: INT_MIN, # INT_MAX + 1 truncated
            -4: INT_MAX, # INT_MIN - 1 truncated
            -5: 0x789abcde, # truncated
            1: -4,
    }.items():
        size = 0
        print("test_handler_bounds_check", size, parameter, end="", flush=True)
        request_data = bytearray(0)
        print(", sending", end="", flush=True)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_BOUNDS_CHECK, request_data, parameter)
        print(", checking", len(result_data), result_value, end="")
        assert result_value == expected_result
        assert len(result_data) == 0
        print(", OK", flush=True)

    # Test - input data size is transferred precisely
    for size in [1, 123, max_data_size]:
        parameter = size
        print("test_handler_bounds_check", size, parameter, end="", flush=True)
        request_data = bytearray(size)
        expected_result = -3
        print(", sending", end="", flush=True)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_BOUNDS_CHECK, request_data, parameter)
        print(", checking", len(result_data), result_value, end="")
        assert result_value == expected_result, (result_value, expected_result)
        assert len(result_data) == 0
        print(", OK", flush=True)

    writer.close()
    await writer.wait_closed()
