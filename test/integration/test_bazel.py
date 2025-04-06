#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Test for Bazel builds.
#

import os
import subprocess
from pathlib import Path

TEST_PATH = Path(__file__).parent.absolute()
PICO_WIFI_SETTINGS_ROOT_PATH = TEST_PATH.parent.parent.absolute()
EXAMPLE_PATH = PICO_WIFI_SETTINGS_ROOT_PATH / "example"

def bazel_build(board_name: str, platform_name: str, wifi_settings_remote: int,
                lwip_config: str, target: str, cwd: Path) -> None:
    subprocess.check_call(["bazel", "clean"], cwd=cwd)
    subprocess.check_call([
        "bazel", "build",
            "--platforms=@pico-sdk//bazel/platform:" + platform_name,
            "--@pico-sdk//bazel/config:PICO_BOARD=" + board_name,
            "--@pico-sdk//bazel/config:PICO_LWIP_CONFIG=" + lwip_config,
            "--@pico-sdk//bazel/config:PICO_STDIO_USB=1",
            "--@pico-wifi-settings//bazel/config:WIFI_SETTINGS_REMOTE=" + str(wifi_settings_remote),
            "--aspects", "@pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect",
            "--output_groups=+pico_uf2_files",
            target,
    ], cwd=cwd)


def test_bazel_example_build_pico_w():
    for wifi_settings_remote in range(3):
        bazel_build(
            board_name = "pico_w",
            platform_name = "rp2040",
            wifi_settings_remote = wifi_settings_remote,
            lwip_config = "//:example_lwipopts",
            target = "//:example",
            cwd = EXAMPLE_PATH)

def test_bazel_example_build_pico2_w():
    for wifi_settings_remote in range(3):
        bazel_build(
            board_name = "pico2_w",
            platform_name = "rp2350",
            wifi_settings_remote = wifi_settings_remote,
            lwip_config = "//:example_lwipopts",
            target = "//:example",
            cwd = EXAMPLE_PATH)

def test_bazel_setup_build_pico_w():
    bazel_build(
        board_name = "pico_w",
        platform_name = "rp2040",
        wifi_settings_remote = 2,
        lwip_config = "//setup:setup_lwipopts",
        target = "//setup:setup",
        cwd = TEST_PATH)

def test_bazel_setup_build_pico2_w():
    bazel_build(
        board_name = "pico2_w",
        platform_name = "rp2350",
        wifi_settings_remote = 2,
        target = "//setup:setup",
        lwip_config = "//setup:setup_lwipopts",
        cwd = TEST_PATH)
