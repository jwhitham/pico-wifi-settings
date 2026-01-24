"""
Convert an update_secret string into a 32-byte hash.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

import hashlib

def update_secret_hash(update_secret_text: str) -> bytes:
    """Turn a secret provided by the user into a 32-byte hash.

    This is derived from:
     - the update_secret= option in remote_picotool.cfg (or the wifi-settings file)
     - the --update-secret or --secret option on the command line
     - the environment variable PICO_UPDATE_SECRET
    """
    secret_hash = b"\x00" * 32
    secret_bytes = update_secret_text.encode("utf-8")
    for i in range(4096):
        secret_hash = hashlib.sha256(secret_hash + secret_bytes).digest()

    return secret_hash
