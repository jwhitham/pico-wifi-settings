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
SERVER_ADDRESS = "localhost"

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.parent.absolute()
TEST_PATH = PICO_WIFI_SETTINGS_ROOT_PATH / "test" / "remote_virtual_c"
REMOTE_PICOTOOL = PICO_WIFI_SETTINGS_ROOT_PATH / "remote_picotool"

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        yield temp_dir

@pytest.mark.asyncio
async def test_virtual_c(temp_dir):
    test_build_path = Path(temp_dir) / "build"
    test_build_path.mkdir()
    cmake_handle = await asyncio.create_subprocess_exec(["cmake", "-DCMAKE_BUILD_DEBUG=1", str(TEST_PATH)], cwd=test_build_path)
    rc = await cmake_handle.wait()
    assert rc == 0
    make_handle = await asyncio.create_subprocess_exec(["make"], cwd=test_build_path)
    rc = await make_handle.wait()
    assert rc == 0
    test_program = test_build_path / "remote_virtual"
    port_file = Path(temp_dir) / "port_file"
    secret = UPDATE_SECRET

    # start server
    test_program_handle = await asyncio.create_subprocess_exec(
            [str(test_program), str(port_file), secret],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Wait for port file to be created (telling us the server's TCP port number)
    port = None
    for attempt in range(100):
        try:
            port = int(port_file.read_text())
        except Exception:
            pass
        if port is not None:
            break
        await asyncio.sleep(0.05)

    assert port is not None

    # connect to server
    remote_picotool_handle = await asyncio.create_subprocess_exec(
            [sys.executable, str(REMOTE_PICOTOOL),
            "--secret", secret, "--address", SERVER_ADDRESS, "--port", str(port),
            "info"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    (stdout_text, stderr_text) = await remote_picotool_handle.communicate()
    rc = await remote_picotool_handle.wait()
    assert rc == 0
    test_program_handle.kill()
    print(stdout_text)
    print(stderr_text)
