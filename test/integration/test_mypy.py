#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# mypy test
#

import subprocess
import sys
from pathlib import Path

PICO_WIFI_SETTINGS_ROOT_PATH = Path(__file__).parent.parent.parent.absolute()

def test_mypy():
    subprocess.check_call([sys.executable, "-m", "mypy", "python"], cwd = PICO_WIFI_SETTINGS_ROOT_PATH)
    subprocess.check_call([sys.executable, "-m", "mypy", "test"], cwd = PICO_WIFI_SETTINGS_ROOT_PATH)
