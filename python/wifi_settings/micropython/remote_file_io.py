#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# This file declares built-in handlers for the remote update service for
# pico-wifi-settings.
#

try:
    import typing
except:
    pass
import struct
import os

FILE_IO_CMD_STRUCT = "<HBB"
FILE_IO_CMD_STRUCT_SIZE = 4
FILE_IO_CMD_GET_FILE_SIZE = 1
FILE_IO_CMD_READ_FROM_FILE = 2
FILE_IO_ERROR_INVALID_SIZE = -1
FILE_IO_ERROR_INVALID_COMMAND = -2
FILE_IO_ERROR_FILE_NAME_UNICODE_ERROR = -3

def file_io_handler(
        msg_type: int,
        data_buffer: bytearray,
        input_data_size: int,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[int, int]:
    """For ID_FILE_IO_HANDLER messages"""

    if input_data_size < FILE_IO_CMD_STRUCT_SIZE:
        return (0, FILE_IO_ERROR_INVALID_SIZE)

    # note 1: input_data_size includes the header, the file name and input data,
    # and result_data_size is the expected size of the result
    offset = input_parameter
    (result_data_size, file_name_size, cmd) = struct.unpack(
            FILE_IO_CMD_STRUCT, data_buffer[:FILE_IO_CMD_STRUCT_SIZE])

    # validate result data size
    if result_data_size > len(data_buffer):
        return (0, FILE_IO_ERROR_INVALID_SIZE)

    # determine the request data size and validate it
    request_data_size = input_data_size - file_name_size - FILE_IO_CMD_STRUCT_SIZE
    if request_data_size < 0:
        return (0, FILE_IO_ERROR_INVALID_SIZE)

    output_data_size = 0
    result_value = 0

    try:
        file_name_bytes = data_buffer[
            FILE_IO_CMD_STRUCT_SIZE : FILE_IO_CMD_STRUCT_SIZE + file_name_size]
        file_name = file_name_bytes.decode()
        if cmd == FILE_IO_CMD_GET_FILE_SIZE:
            with open(file_name, "rb") as fd:
                # seek to the end to get the size
                fd.seek(0, 2)
                file_size = fd.tell()
                output_data_size = 4
                data_buffer[:output_data_size] = struct.pack("<I", file_size)

        elif cmd == FILE_IO_CMD_READ_FROM_FILE:
            with open(file_name, "rb") as fd:
                # read up to output_data_size bytes starting at offset
                fd.seek(offset, 0)
                output_data_size = fd.readinto(data_buffer)
        else:
            # invalid command
            result_value = FILE_IO_ERROR_INVALID_COMMAND

    except UnicodeError as x:
        result_value = FILE_IO_ERROR_FILE_NAME_UNICODE_ERROR
    except OSError as x:
        result_value = x.errno

    return (output_data_size, result_value)
