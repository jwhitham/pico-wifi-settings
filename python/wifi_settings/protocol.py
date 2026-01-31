"""
Protocol constants

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .aes import AES_BLOCK_SIZE

CHALLENGE_SIZE = 15
AUTHENTICATION_SIZE = 15
DATA_HASH_SIZE = 7

PAD_BLOCK_1 = b"\x00" * (AES_BLOCK_SIZE - 1)

HMAC_BLOCK_SIZE = 64
HMAC_DIGEST_SIZE = 32

# Note- the structure of a reply_header or request_header is as follows:
# typedef struct enc_message_header_t {
#    uint32_t    data_size;
#    int32_t     parameter_or_result;
#    uint8_t     msg_type;
#    uint8_t     data_hash[DATA_HASH_SIZE];
# } enc_message_header_t;
# The size of this structure should be AES_BLOCK_SIZE
HEADER_STRUCT = "<IiB7s"
HEADER_DATA_HASH_OFFSET = AES_BLOCK_SIZE - DATA_HASH_SIZE

RESPONDER_REQUEST_MAGIC =  b"PWS?"
RESPONDER_REPLY_MAGIC =    b"PWS:"
RESPONDER_MAX_SIZE =        20

def get_pad_bytes(data_size: int) -> bytes:
    """Pad data so that it is a multiple of AES_BLOCK_SIZE."""
    last_block_size = data_size % AES_BLOCK_SIZE
    if last_block_size == 0:
        return b""
    pad = AES_BLOCK_SIZE - last_block_size
    return b"\x00" * pad
