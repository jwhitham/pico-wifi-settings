#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Build tool for release binaries and size info table
#

import json
import os
import re
import shutil
import subprocess
import tempfile
import typing
from pathlib import Path

BOARDS = ["pico_w", "pico2_w"]

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.absolute()
PICO_SDK_PATH = Path(os.environ.get("PICO_SDK_PATH",
        str(PICO_WIFI_SETTINGS_ROOT_PATH / "../pico-sdk")))

def do_build(src_dir: str, target_file: typing.Optional[Path],
            elf_file: Path, cmake_args: typing.List[str]) -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        project_dir = Path(tmp_dir) / "wifi_settings"
        build_dir = Path(tmp_dir) / "build"
        sdk_dir = Path(tmp_dir) / "sdk"
        os.symlink(src = PICO_WIFI_SETTINGS_ROOT_PATH,
                   dst = project_dir,
                   target_is_directory = True)
        os.symlink(src = PICO_SDK_PATH,
                   dst = sdk_dir,
                   target_is_directory = True)
        build_dir.mkdir()
        env = dict(os.environ)
        env["PICO_SDK_PATH"] = str(sdk_dir)
        subprocess.check_call(["cmake", str(project_dir / src_dir)] + cmake_args,
                              cwd = build_dir, env=env)
        subprocess.check_call(["make"], cwd = build_dir)

        raw_binaries = list(build_dir.glob("*.bin"))
        assert len(raw_binaries) != 0
        assert len(raw_binaries) == 1

        uf2_binaries = list(build_dir.glob("*.uf2"))
        assert len(uf2_binaries) != 0
        assert len(uf2_binaries) == 1

        elf_binaries = list(build_dir.glob("*.elf"))
        assert len(elf_binaries) != 0
        assert len(elf_binaries) == 1

        size = Path(raw_binaries[0]).stat().st_size
        shutil.move(elf_binaries[0], elf_file)

        if target_file:
            shutil.move(uf2_binaries[0], target_file)

    return size

def main() -> None:
    # Check consistency of working directory
    check = subprocess.run(["git", "status"],
                cwd=PICO_WIFI_SETTINGS_ROOT_PATH,
                stdout=subprocess.PIPE, text=True, check=True).stdout
    if "nothing to commit, working tree clean" not in check:
        raise Exception("Checkout is not clean!")

    # Git commit
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"],
                cwd=PICO_WIFI_SETTINGS_ROOT_PATH,
                stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    git_commit = git_commit[:16]
    if not git_commit:
        raise Exception("Unable to determine git commit")

    # Version
    re_version = re.compile(r'^set.WIFI_SETTINGS_VERSION_STRING "(.+)".*$')
    version = ""
    for line in open(PICO_WIFI_SETTINGS_ROOT_PATH / "CMakeLists.txt", "rt"):
        m = re_version.match(line)
        if m is not None:
            version = m.group(1)
        
    if not version:
        raise Exception("Unable to determine library version")

    # Create output directory
    target_path = PICO_WIFI_SETTINGS_ROOT_PATH / "release"
    if target_path.exists():
        shutil.rmtree(str(target_path))
    target_path.mkdir()
    setup_target_path = target_path / "setup"
    setup_target_path.mkdir()
    setup_uf2_target_path = setup_target_path / f"pico-wifi-settings-{version}"
    setup_uf2_target_path.mkdir()
    (target_path / "build_info.json").write_text(json.dumps({
        "git_commit": git_commit,
        "version": version,
    }, indent=4))

    # Estimated size impact of wifi-settings
    sizes: typing.Dict[typing.Any, int] = {}
    for (test_mode, remote_level) in [
            ("basic", 0),
            ("wifi_settings", 0),
            ("wifi_settings", 1),
            ("wifi_settings", 2),
            ("no_wifi", 0),
            ("basic_with_mbedtls", 0),
    ]:
        board = BOARDS[-1]
        key = f"{test_mode}_{remote_level}"
        sizes[key] = do_build(
            src_dir="test/size",
            target_file=None,
            elf_file=target_path / f"size_test_{key}.elf",
            cmake_args=[f"-DPICO_BOARD={board}",
                        f"-DWIFI_SETTINGS_REMOTE={remote_level}",
                        f"-DTEST_MODE={test_mode}"])

    sizes["wifi_size"] = sizes["basic_0"] - sizes["no_wifi_0"]
    sizes["min_size"] = sizes["wifi_settings_0"] - sizes["basic_0"]
    sizes["mid_size"] = sizes["wifi_settings_2"] - sizes["basic_with_mbedtls_0"]
    sizes["max_size"] = sizes["wifi_settings_2"] - sizes["basic_0"]
    (target_path / "sizes.json").write_text(json.dumps(sizes, indent=4))

    # Begin compiling stuff - here is the setup app
    for board in BOARDS:
        do_build(
            src_dir="setup",
            target_file=setup_uf2_target_path / f"setup_app__{board}__{version}.uf2",
            elf_file=target_path / f"setup_app__{board}__{version}.elf",
            cmake_args=[f"-DPICO_BOARD={board}",
                        f"-DWIFI_SETTINGS_REMOTE=2",
                        f"-DDEMO_GIT_COMMIT={git_commit}"])

    # Build the example (to check it builds)
    for board in BOARDS:
        do_build(
            src_dir="example",
            target_file=None,
            elf_file=target_path / f"example__{board}__{version}.elf",
            cmake_args=[f"-DPICO_BOARD={board}"])

    # store release artefacts
    shutil.make_archive(
        base_name=str(target_path / f"release-{version}-{git_commit}"),
        format="zip",
        root_dir=setup_target_path)


if __name__ == "__main__":
    main()
