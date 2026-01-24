"""
Remote file I/O client.

This uses ID_FILE_IO_HANDLER on the remote. Simple file I/O requests
are served via the remote handler API.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .handler_ids import *
from .exceptions import *
from .asyncio_client import Client
from .pico_info import PicoInfo

import struct
import typing

FILE_IO_CMD_STRUCT = "<HBB"
FILE_IO_CMD_STRUCT_SIZE = 4
FILE_IO_CMD_GET_FILE_SIZE = 1
FILE_IO_CMD_READ_FROM_FILE = 2
FILE_IO_ERROR_INVALID_SIZE = -1
FILE_IO_ERROR_INVALID_COMMAND = -2
FILE_IO_ERROR_FILE_NAME_UNICODE_ERROR = -3

class RemoteFileIO:
    def __init__(self, client: Client, pico_info: PicoInfo) -> None:
        """
        Remote file I/O client.

        This uses the ID_FILE_IO_HANDLER on the remote.

        Copyright (c) 2026 Jack Whitham

        SPDX-License-Identifier: BSD-3-Clause
        """
        self.client = client
        self.max_data_size = pico_info.max_data_size

    def __build_request_header(self, cmd: int, file_name: str,
                    result_data_size: int = 0) -> bytes:
        """
        Private function to build the header of a file I/O request.

        Each request has:
            parameter = request offset
            request_data:
                result_data_size        2 bytes, unsigned
                file_name_size          1 byte, unsigned
                cmd                     1 byte
                file_name               file_name_size bytes
                request_data            <remaining bytes>
        
        This function generates the first four fields.
        """

        # file name must be encoded to UTF-8 in order to be sent
        # and the file name size must fit in one byte
        file_name_bytes = file_name.encode()
        file_name_size = len(file_name_bytes)

        # basic validity checks on the provided data
        if (file_name_size > 0xff) or (file_name_size <= 0):
            raise LocalError("file name is not valid")
        if (cmd > 0xff) or (cmd <= 0):
            raise LocalError("cmd is not valid")
        if result_data_size < 0:
            raise LocalError("result_data_size is not valid")

        # check the result size
        if result_data_size > self.max_data_size:
            raise TooLargeError("MAX_DATA_SIZE would be exceeded when receiving")

        # determine the maximum possible size for request data
        max_request_size = (self.max_data_size - file_name_size
                            - FILE_IO_CMD_STRUCT_SIZE)

        return struct.pack(FILE_IO_CMD_STRUCT, result_data_size,
                    file_name_size, cmd) + file_name_bytes

    def get_max_request_size(self, file_name: str) -> int:
        """Get the maximum possible size for a request on a particular file."""
        return self.max_data_size - len(self.__build_request_header(0, file_name, 0))

    def get_max_result_size(self) -> int:
        """Get the maximum possible size for a result."""
        return self.max_data_size

    async def __command(self, cmd: int, file_name: str, request_data: bytes = b"", offset: int = 0, result_data_size: int = 0) -> bytes:
        """Run a file I/O command on the remote side."""

        # Add header to request_data
        request_data = self.__build_request_header(cmd, file_name, result_data_size) + request_data
        if len(request_data) > self.max_data_size:
            raise TooLargeError("MAX_DATA_SIZE would be exceeded when sending")

        # run the handler on the remote
        try:
            (result_data, result_value) = await self.client.run(ID_FILE_IO_HANDLER,
                request_data=request_data, parameter=offset)
        except BadHandlerError:
            raise RemoteError("file_io handler error") from None

        # convert the return code to an error if required
        if result_value > 0:
            # These are errors from a system call i.e. errno
            if result_value == 2:
                raise FileNotFoundError(file_name)
            raise RemoteError(os.strerror(result_value))
        if result_value < 0:
            if result_value == FILE_IO_ERROR_FILE_NAME_UNICODE_ERROR:
                # This should not happen as the UTF-8 encoding ought to be valid
                raise RemoteError("unable to decode filename UTF-8 on remote")
            if result_value == FILE_IO_ERROR_INVALID_SIZE:
                # This should not happen as the size is checked before sending it
                raise RemoteError("size error reported by remote side")
            if result_value == FILE_IO_ERROR_INVALID_COMMAND:
                # This might happen if the requested command is not known
                raise RemoteError("invalid file IO command")
            # These are unknown errors from the handler
            raise RemoteError("file IO error " + str(result_value))

        return result_data

    async def get_file_size(self, file_name: str) -> int:
        """Determine the size of a file on the remote."""
        result_data = await self.__command(
                cmd=FILE_IO_CMD_GET_FILE_SIZE,
                file_name=file_name)
        if len(result_data) != 4:
            raise RemoteError("expected exactly 4 bytes")
        return struct.unpack("<I", result_data)[0]

    async def read_bytes(self, file_name: str) -> bytes:
        """Read the contents of a file on the remote."""
        block_size = self.get_max_result_size()
        offset = 0
        output: typing.List[bytes] = []
        read_ok = True
        while read_ok:
            result_data = await self.__command(
                    cmd=FILE_IO_CMD_READ_FROM_FILE,
                    file_name=file_name,
                    result_data_size=block_size,
                    offset=offset)
            output.append(result_data)
            offset += len(result_data)
            read_ok = (len(result_data) >= block_size)

        return b"".join(output)
