#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Test for pico-wifi-settings example.
#

import os
import subprocess
import tempfile
from pathlib import Path

TEST_PATH = Path(__file__).parent.absolute()
PICO_WIFI_SETTINGS_ROOT_PATH = TEST_PATH.parent.parent.absolute()
EXAMPLE_PATH = PICO_WIFI_SETTINGS_ROOT_PATH / "example"
PICO_SDK_PATH = Path(os.environ.get("PICO_SDK_PATH",
            str(PICO_WIFI_SETTINGS_ROOT_PATH / "../pico-sdk")))

def test_pico_sdk_path():
    assert (PICO_SDK_PATH / "CMakeLists.txt").is_file(), ("Missing Pico SDK - set PICO_SDK_PATH environment variable")

def env_with_pico_sdk():
    env = dict(os.environ)
    env["PICO_SDK_PATH"] = PICO_SDK_PATH
    return env

def test_example():
    with tempfile.TemporaryDirectory() as td:
        build_dir = Path(td)

        subprocess.check_call(["cmake",
            str(EXAMPLE_PATH),
            "-DPICO_BOARD=pico_w"], cwd = build_dir,
            env = env_with_pico_sdk())
        subprocess.check_call(["make"], cwd = build_dir)
        
        assert (build_dir / "example.uf2").is_file()
