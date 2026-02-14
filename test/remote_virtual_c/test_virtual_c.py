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

UPDATE_SECRET = "OWL001"
SERVER_ADDRESS = "127.0.0.1"

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.parent.absolute()
TEST_PATH = PICO_WIFI_SETTINGS_ROOT_PATH / "test" / "remote_virtual_c"
REMOTE_PICOTOOL = PICO_WIFI_SETTINGS_ROOT_PATH / "remote_picotool"

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
async def test_virtual_c(temp_dir):
    server_handle = ServerHandle(temp_dir)
    await server_handle.start()

    # connect to server
    remote_picotool_handle = await asyncio.create_subprocess_exec(
            sys.executable, str(REMOTE_PICOTOOL),
            "--secret", UPDATE_SECRET, "--address", SERVER_ADDRESS,
            "--port", str(server_handle.tcp_port),
            "info",
            stdout=subprocess.PIPE)
    (stdout_bytes, _) = await remote_picotool_handle.communicate()
    text = stdout_bytes.decode("utf-8", errors="ignore")
    print(text)
    rc = await remote_picotool_handle.wait()
    assert rc == 0
    assert "123456789ABCDEF0" in text   # fake board id
    assert "test-host-name" in text
