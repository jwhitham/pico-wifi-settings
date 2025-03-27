#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Integration test for pico-wifi-settings.
#
# This test uses a skeleton Pico project. The project is extended
# with pico-wifi-settings support according to the integration instructions
# in ../../README.md. Then the test ensures it can be built.
#

import pytest
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BUILD_DIR = "build"
TEST_PATH = Path(__file__).parent.absolute()
PICO_WIFI_SETTINGS_ROOT_PATH = TEST_PATH.parent.parent.absolute()
PICO_SDK_PATH = Path(os.environ.get("PICO_SDK_PATH",
        str(PICO_WIFI_SETTINGS_ROOT_PATH / "../pico-sdk")))

def test_pico_sdk_path():
    assert (PICO_SDK_PATH / "CMakeLists.txt").is_file(), ("Missing Pico SDK - set PICO_SDK_PATH environment variable")

def env_with_pico_sdk():
    env = dict(os.environ)
    env["PICO_SDK_PATH"] = PICO_SDK_PATH
    return env

@pytest.fixture
def unmodified_project_dir():
    with tempfile.TemporaryDirectory() as td:
        project_dir = Path(td)
        shutil.copy(TEST_PATH / "CMakeLists.txt", project_dir)
        shutil.copy(TEST_PATH / "test.c", project_dir)
        shutil.copy(PICO_WIFI_SETTINGS_ROOT_PATH / "example" / "pico_sdk_import.cmake", project_dir)

        os.mkdir(project_dir / BUILD_DIR)
        yield project_dir

def do_build(build_dir, cmake_args):
    subprocess.check_call(["cmake", "..", "-DPICO_BOARD=pico_w"] + cmake_args,
                          cwd = build_dir, env=env_with_pico_sdk())
    subprocess.check_call(["make"], cwd = build_dir)
    assert (build_dir / "test.uf2").is_file()
    map_file = (build_dir / "test.elf.map")
    assert map_file.is_file()
    return map_file.read_text()

@pytest.fixture
def modified_project_dir(unmodified_project_dir):
    project_dir = unmodified_project_dir

    # Integration into your own Pico application requires 4 steps:
    # 1. Import pico-wifi-settings
    os.symlink(src = PICO_WIFI_SETTINGS_ROOT_PATH, dst = project_dir / "wifi_settings", target_is_directory = True)

    # 2. Modify CMakeLists.txt to import the library
    # ... with substep - add pico_cyw43_arch_lwip_...
    modify_0 = (project_dir / "CMakeLists.txt").read_text()
    marker = "pico_sdk_init()"
    modify_1 = modify_0.replace(marker, marker + "\nadd_subdirectory(wifi_settings build)\n")
    assert modify_1 != modify_0
    marker = "target_link_libraries(test "
    modify_2 = modify_1.replace(marker, marker + " pico_cyw43_arch_lwip_threadsafe_background wifi_settings ")
    assert modify_2 != modify_1
    (project_dir / "CMakeLists.txt").write_text(modify_2)

    # ... with substep - add lwipopts.h
    shutil.copy(PICO_WIFI_SETTINGS_ROOT_PATH / "example" / "lwipopts.h", project_dir)

    # ... with substep - add mbedtls_config.h
    shutil.copy(PICO_WIFI_SETTINGS_ROOT_PATH / "example" / "mbedtls_config.h", project_dir)

    # 3. Include the header file
    modify_0 = (project_dir / "test.c").read_text()
    marker = '#include "pico/stdlib.h"'
    modify_1 = modify_0.replace(marker, marker +
        '\n#include <wifi_settings.h>')
    assert modify_1 != modify_0

    # 4. Modify your main function
    marker = "stdio_init_all();"
    modify_2 = modify_1.replace(marker, marker +
        '\nif (wifi_settings_init() != 0) { panic("error"); }\n' +
        'wifi_settings_connect();\n')
    assert modify_2 != modify_1
    (project_dir / "test.c").write_text(modify_2)

    return project_dir

def test_build_unmodified_project(unmodified_project_dir):
    map_text = do_build(unmodified_project_dir / BUILD_DIR, [])
    assert "wifi_settings_disconnect" not in map_text
    assert "wifi_settings_remote_init" not in map_text
    assert "wifi_settings_ota_firmware_update_handler2" not in map_text

def test_build_modified_project_remote_0(modified_project_dir):
    Path(modified_project_dir / "mbedtls_config.h").unlink() # not required without remote
    map_text = do_build(modified_project_dir / BUILD_DIR, ["-DWIFI_SETTINGS_REMOTE=0"])
    assert "wifi_settings_disconnect" in map_text
    assert "wifi_settings_remote_init" not in map_text
    assert "wifi_settings_ota_firmware_update_handler2" not in map_text

def test_build_modified_project_remote_1(modified_project_dir):
    map_text = do_build(modified_project_dir / BUILD_DIR, [])
    assert "wifi_settings_disconnect" in map_text
    assert "wifi_settings_remote_init" in map_text
    assert "wifi_settings_ota_firmware_update_handler2" not in map_text

def test_build_modified_project_remote_2(modified_project_dir):
    map_text = do_build(modified_project_dir / BUILD_DIR, ["-DWIFI_SETTINGS_REMOTE=2"])
    assert "wifi_settings_disconnect" in map_text
    assert "wifi_settings_remote_init" in map_text
    assert "wifi_settings_ota_firmware_update_handler2" in map_text
