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
import shutil
import struct
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
    debug_temp_dir = os.getenv("DEBUG_TEMP_DIR", "")
    if debug_temp_dir:
        temp_dir = Path(debug_temp_dir)
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir))
        temp_dir.mkdir(exist_ok=True)
        yield temp_dir
    else:
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
                remote_picotool.Client, asyncio.StreamWriter, wifi_settings.PicoInfo]:
    # Make a new connection to the server and get the max_data_size and other info
    reader, writer = await remote_picotool.get_pico_connection(config)
    client = remote_picotool.Client(config.update_secret_hash, reader, writer)
    (result_data, result_value) = await client.run(wifi_settings.ID_PICO_INFO_HANDLER)
    pico_info = wifi_settings.PicoInfo(result_data)
    return (client, writer, pico_info)

@pytest.mark.asyncio
async def test_out_of_range_data(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, pico_info) = await connect(server_handle.config)
    max_data_size = pico_info.max_data_size
    writer.close()
    await writer.wait_closed()

    # Test - out of range data sizes
    for size in [max_data_size + 1, -1, max_data_size + (1 << 32)]:
        reader, writer = await remote_picotool.get_pico_connection(server_handle.config)
        client = remote_picotool.Client(server_handle.config.update_secret_hash, reader, writer)
        try:
            print("out of range data size", size, flush=True)
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
    (client, writer, pico_info) = await connect(server_handle.config)
    max_data_size = pico_info.max_data_size

    # Test - sending and receiving data of various sizes
    sizes = [16, 1, 15, 17, 0, 500, 511, 513,
            max_data_size // 2,
            (max_data_size // 2) + 1,
            max_data_size, max_data_size - 1]
    for size in sizes:
        assert size <= max_data_size
        parameter = -size
        print("test_echo_xor_count", size, parameter, flush=True)
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
    (client, writer, pico_info) = await connect(server_handle.config)
    max_data_size = pico_info.max_data_size

    # Test - receiving more data than was sent
    sizes = [16, 1, 15, 17, 0, 500, 511, 513, max_data_size, max_data_size - 1,
            -1, max_data_size + 1, INT_MIN, INT_MAX]
    for parameter in sizes:
        size = 0
        print("test_gen_output", size, parameter, flush=True)
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

        print("sending", flush=True)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_GEN_OUTPUT, request_data, parameter)
        print("checking: len(result_data) = {} expected {}".format(
                len(result_data), len(expected_result_data)))
        print("checking: result_value = {} expected {}".format(
                result_value, expected_result))
        assert result_value == expected_result
        assert len(result_data) == len(expected_result_data)
        assert result_data == bytes(expected_result_data)
        print("OK", flush=True)

    writer.close()
    await writer.wait_closed()

@pytest.mark.asyncio
async def test_bounds_check(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, pico_info) = await connect(server_handle.config)
    max_data_size = pico_info.max_data_size

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
        print("test_bounds_check (part 1)", size, parameter, flush=True)
        request_data = bytearray(0)
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_BOUNDS_CHECK, request_data, parameter)
        print("checking", len(result_data), result_value)
        assert result_value == expected_result
        assert len(result_data) == 0
        print("OK", flush=True)

    # Test - input data size is transferred precisely
    for size in [1, 123, max_data_size]:
        parameter = size
        print("test_bounds_check (part 2)", size, parameter, flush=True)
        request_data = bytearray(size)
        expected_result = -3
        (result_data, result_value) = await client.run(ID_TEST_HANDLER_BOUNDS_CHECK, request_data, parameter)
        print("checking", len(result_data), result_value, flush=True)
        assert result_value == expected_result, (result_value, expected_result)
        assert len(result_data) == 0
        print("OK", flush=True)

    writer.close()
    await writer.wait_closed()

def create_remote_picotool_subprocess_args(server_handle: ServerHandle) -> typing.List[str]:
    return [sys.executable,
            str(PICO_WIFI_SETTINGS_ROOT_PATH / "remote_picotool"),
            "--board-address", SERVER_ADDRESS,
            "--port", str(server_handle.tcp_port),
            "--update-secret", UPDATE_SECRET,
            ]

@pytest.mark.asyncio
async def test_info_via_subprocess(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()

    make_handle = await asyncio.create_subprocess_exec(
            *create_remote_picotool_subprocess_args(server_handle),
            "info",
            stdout=asyncio.subprocess.PIPE)
    (stdout, _) = await make_handle.communicate()
    assert make_handle.returncode == 0
    stdout_text = stdout.decode()
    print(stdout_text)
    assert "123456789ABCDEF0" in stdout_text
    assert "test-host-name" in stdout_text

@pytest.mark.asyncio
async def test_ota_via_subprocess(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()

    test_data = os.urandom(9753)
    ota_send_file = temp_dir / "ota_send.bin"
    ota_send_file.write_bytes(test_data)

    make_handle = await asyncio.create_subprocess_exec(
            *create_remote_picotool_subprocess_args(server_handle),
            "ota", str(ota_send_file),
            stdout=asyncio.subprocess.PIPE)
    (stdout, _) = await make_handle.communicate()
    stdout_text = stdout.decode()
    print(stdout_text)
    assert make_handle.returncode == 0

    # check what was received
    ota_receive_file = temp_dir / "ota.bin"
    assert ota_receive_file.is_file()
    received_data = ota_receive_file.read_bytes()
    assert received_data.startswith(test_data)
    assert set(received_data[len(test_data):]) == set([255])

@pytest.mark.asyncio
async def test_wifi_file_update_reboot_test(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, pico_info) = await connect(server_handle.config)
    (file_start, file_end) = pico_info.flash_wifi_settings_file_range
    file_size = min(file_end - file_start, pico_info.max_data_size)
    writer.close()
    await writer.wait_closed()
    print(f"file size: {file_size}")

    receive_file = temp_dir / "wifi_settings.bin"
    reboot_file = temp_dir / "reboot.bin"

    for (request_size_multiplier, msg_type, parameter, scenario) in [
        (  0, wifi_settings.ID_UPDATE_HANDLER, 0,        "update with empty file"),
        (100, wifi_settings.ID_UPDATE_HANDLER, 0,        "update with new file (all bytes)"),
        ( 99, wifi_settings.ID_UPDATE_HANDLER, 0,        "update with new file (most bytes)"),
        (  0, wifi_settings.ID_UPDATE_REBOOT_HANDLER, 0, "reboot only"),
        (100, wifi_settings.ID_UPDATE_REBOOT_HANDLER, 0, "update file (all bytes) and then reboot"),
        ( 98, wifi_settings.ID_UPDATE_REBOOT_HANDLER, 0, "update file (most bytes) and then reboot"),
        (100, wifi_settings.ID_UPDATE_REBOOT_HANDLER, 1, "update file then reboot to bootloader"),
        (  0, wifi_settings.ID_UPDATE_REBOOT_HANDLER, 1, "reboot to bootloader"),
    ]:
        print(f"test_wifi_file_update_reboot_test: {scenario}")
        request_data = os.urandom((file_size * request_size_multiplier) // 100)

        reader, writer = await remote_picotool.get_pico_connection(server_handle.config)
        client = remote_picotool.Client(server_handle.config.update_secret_hash, reader, writer)
        print(f"send {len(request_data)} bytes with msg_type {msg_type} and parameter {parameter}", flush=True)
        (result_data, result_value) = await client.run(msg_type, request_data, parameter)
        print(f"returns {len(result_data)} bytes with value {result_value}")

        assert result_value >= 0, result_value

        if msg_type == wifi_settings.ID_UPDATE_REBOOT_HANDLER:
            # File is rewritten if the length is greater than 0
            # Always reboots
            # Reboot to bootloader if parameter == 1
            # result_value is the parameter
            assert reboot_file.exists()
            assert reboot_file.read_bytes()[0] == parameter
            reboot_file.unlink()
            assert result_value == parameter, result_value
            assert len(result_data) == 0
            if len(request_data) != 0:
                # File is rewritten
                assert receive_file.exists()
            else:
                # File is not rewritten
                assert not receive_file.exists()
        else:
            # File is always rewritten (even with 0 length)
            # Never reboots
            # result_value is the file size
            assert not reboot_file.exists()
            assert receive_file.exists()
            assert result_value == len(request_data), result_value
            assert len(result_data) == 0

        if receive_file.exists():
            # Check file contents
            assert receive_file.read_bytes() == request_data
            receive_file.unlink()
        
        writer.close()
        await writer.wait_closed()

@pytest.mark.asyncio
async def test_read_write(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()
    (client, writer, pico_info) = await connect(server_handle.config)

    expect = []
    for (test_data_size, offset, scenario) in [
        (pico_info.flash_sector_size, 0, "small write"),
        (pico_info.flash_sector_size, pico_info.flash_sector_size, "small write with offset"),
        (pico_info.max_data_size, pico_info.flash_sector_size * 2, "large write"),
    ]:
        # test data
        test_data = os.urandom(test_data_size)
        test_address = pico_info.flash_reusable_range[0] + offset
        print(f"test_read_write: {scenario}: {test_address:08x} {test_address + test_data_size:08x}")

        # write a memory block
        request_data = test_data
        parameter = test_address
        (result_data, result_value) = await client.run(wifi_settings.ID_FLASH_WRITE_HANDLER, request_data, parameter)
        assert len(result_data) == 0
        assert result_value == 0

        expect.append((test_address, test_data))
    
    for (test_address, test_data) in expect:
        # read it back
        print(f"test_read_write: readback: {test_address:08x} + {pico_info.logical_offset:08x}")
        request_data = struct.pack("<II", test_address + pico_info.logical_offset, test_address + len(test_data) + pico_info.logical_offset)
        parameter = 0
        (result_data, result_value) = await client.run(wifi_settings.ID_READ_HANDLER, request_data, parameter)
        assert result_value == 0
        assert len(result_data) == len(test_data)
        assert result_data == test_data
        
    writer.close()
    await writer.wait_closed()
