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

@pytest.mark.asyncio
async def test_virtual_c(temp_dir):
    test_build_path = Path(temp_dir) / "build"
    test_build_path.mkdir()
    print("cmake", flush=True)
    cmake_handle = await asyncio.create_subprocess_exec("cmake", "-DCMAKE_BUILD_DEBUG=1", str(TEST_PATH),
        cwd=str(test_build_path))
    rc = await cmake_handle.wait()
    assert rc == 0
    print("make", flush=True)
    make_handle = await asyncio.create_subprocess_exec("make", cwd=str(test_build_path))
    rc = await make_handle.wait()
    assert rc == 0

    test_program = test_build_path / "remote_virtual"
    port_file = Path(temp_dir) / "port_file"
    secret = UPDATE_SECRET
    assert test_program.exists()
    assert REMOTE_PICOTOOL.exists()

    # start server
    print("server", flush=True)
    test_program_handle = await asyncio.create_subprocess_exec(str(test_program), str(port_file), secret)

    try:
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

        print("port is", port)
        assert port is not None, "server subprocess did not create port file " + str(port_file)

        # connect to server
        print("remote_picotool", flush=True)
        remote_picotool_handle = await asyncio.create_subprocess_exec(
                sys.executable, str(REMOTE_PICOTOOL),
                "--secret", secret, "--address", SERVER_ADDRESS, "--port", str(port),
                "info",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            print("communicate")
            (stdout_bytes, stderr_bytes) = await remote_picotool_handle.communicate()
            print("****")
            print(stdout_bytes.decode("utf-8", errors="ignore"))
            print("****")
            print(stderr_bytes.decode("utf-8", errors="ignore"))
            print("****")
            rc = await remote_picotool_handle.wait()
            assert rc == 0
        finally:
            try: 
                remote_picotool_handle.kill()
            except Exception:
                pass
    finally:
        try: 
            test_program_handle.kill()
        except Exception:
            pass
