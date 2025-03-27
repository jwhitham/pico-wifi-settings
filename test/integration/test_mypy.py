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

TEST_PATH = Path(__file__).parent.parent.absolute()

def test_mypy():
    subprocess.check_call([sys.executable, "-m", "mypy", "."], cwd = TEST_PATH)
