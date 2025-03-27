#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Unit tests for pico-wifi-settings.
#

import subprocess
import tempfile
from pathlib import Path

TEST_PATH = Path(__file__).parent.absolute()

def test_units():
    with tempfile.TemporaryDirectory() as td:
        build_dir = Path(td)
        try:
            subprocess.check_call(["cmake", str(TEST_PATH)], cwd = build_dir)
            subprocess.check_call(["make"], cwd = build_dir)
            subprocess.check_call(["make", "test"], cwd = build_dir)
        finally:
            for log in sorted(build_dir.rglob("*.log")):
                print(log.read_text())
