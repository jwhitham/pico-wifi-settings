"""
Protocol constants

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .aes import AES_BLOCK_SIZE

CHALLENGE_SIZE = 15
AUTHENTICATION_SIZE = 15
DATA_HASH_SIZE = 7

HEADER_SIZE = AES_BLOCK_SIZE - DATA_HASH_SIZE
PAD_BLOCK_1 = b"\x00" * (AES_BLOCK_SIZE - 1)

def get_pad_bytes(data_size: int) -> bytes:
    """Pad data so that it is a multiple of AES_BLOCK_SIZE."""
    last_block_size = data_size % AES_BLOCK_SIZE
    if last_block_size == 0:
        return b""
    pad = AES_BLOCK_SIZE - last_block_size
    return b"\x00" * pad
