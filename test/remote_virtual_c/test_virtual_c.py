#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# mypy test
#

import asyncio
import pytest
import subprocess
import sys
import tempfile
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

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        yield temp_dir

class ServerHandle:
    def __init__(self, temp_dir):
        self.test_build_path = Path(temp_dir) / "build"
        self.test_program = self.test_build_path / "remote_virtual"
        self.server_handle = None
        self.tcp_port_file = Path(temp_dir) / "tcp_port_file"
        self.udp_port_file = Path(temp_dir) / "udp_port_file"
        self.tcp_port = -1
        self.udp_port = -1
        self.config = remote_picotool.BaseRemotePicotoolCfg()

    async def start(self) -> None:
        self.test_build_path.mkdir()
        print("cmake", flush=True)
        cmake_handle = await asyncio.create_subprocess_exec("cmake", "-DCMAKE_BUILD_DEBUG=1", str(TEST_PATH),
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
                str(self.test_program),
                str(self.tcp_port_file),
                str(self.udp_port_file),
                UPDATE_SECRET)

        self.tcp_port = await self.read_port_file(self.tcp_port_file)
        self.udp_port = await self.read_port_file(self.udp_port_file)

        self.config.set("update_secret", UPDATE_SECRET)
        self.config.set("board_address", SERVER_ADDRESS)
        self.config.set("port", str(self.tcp_port))

    async def read_port_file(self, file_path: Path) -> int:
        # Wait for port file to be created (telling us the server's TCP port number)
        port = -1
        for attempt in range(100):
            try:
                port = int(file_path.read_text())
            except Exception:
                pass

            if port >= 0:
                return port

            await asyncio.sleep(0.05)

        assert False, "server subprocess did not create port file " + str(file_path)

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

@pytest.mark.asyncio
async def test_out_of_range_data_1(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()

    # get max_data_size
    reader, writer = await remote_picotool.get_pico_connection(server_handle.config)
    client = remote_picotool.Client(server_handle.config.update_secret_hash, reader, writer)
    (result_data, result_value) = await client.run(wifi_settings.ID_PICO_INFO_HANDLER)
    max_data_size = wifi_settings.PicoInfo(result_data).max_data_size
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
    assert False        
