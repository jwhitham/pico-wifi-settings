"""
File reader for firmware files (.uf2, .elf, .bin).

This is used when applying over-the-air updates to Pico devices
running C/C++ firmware built with the Pico SDK.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..handler_ids import *
from ..exceptions import *
from .client import Client

from abc import abstractmethod
from pathlib import Path

import enum
import struct
import typing

MAX_WIFI_SETTINGS_FILE_SIZE = 4096

class FileType(enum.Enum):
    NOT_FOUND = enum.auto()
    UF2 = enum.auto()
    ELF = enum.auto()
    BINARY = enum.auto()
    WIFI_SETTINGS = enum.auto()

def get_file_type(filename: Path) -> FileType:
    """Examine a file provided by the user and classify it."""

    if not filename.exists():
        return FileType.NOT_FOUND

    if not filename.is_file():
        raise LocalError(f"Not a file: '{filename}'")

    with open(filename, "rb") as fd:
        sample = fd.read(MAX_WIFI_SETTINGS_FILE_SIZE + 1)
        magic = sample[:4]
    
    if magic == b"UF2\n":
        return FileType.UF2
    if magic == b"\x7fELF":
        return FileType.ELF
    if len(sample) > MAX_WIFI_SETTINGS_FILE_SIZE:
        return FileType.BINARY

    # Check if file is valid UTF-8 (aside from "unused Flash" file characters, 0xff)
    sample = sample.rstrip(b"\xff") + b"\x1b\x00\x1b" # <<TEST
    utf8_check = sample.decode("utf-8", errors="ignore").encode("utf-8")
    if len(utf8_check) == len(sample):
        # Valid UTF-8 aside from unused Flash characters
        return FileType.WIFI_SETTINGS

    return FileType.BINARY

class FileReader:
    def __init__(self, pico_info: PicoInfo, family: Family) -> None:
        self.pico_info = pico_info
        self.family = family
        self.data = bytes()
        self.flash_offset = 0

    @abstractmethod
    def read(self, filename: Path) -> None:
        pass

    def set_lower_bound(self, flash_offset: int) -> None:
        self.flash_offset = flash_offset
   
    @property
    def lower_bound(self) -> int:
        return self.flash_offset

    @property
    def upper_bound(self) -> int:
        return self.flash_offset + len(self.data)

    @property
    def size(self) -> int:
        return len(self.data)

    def get_sha256(self) -> bytes:
        return hashlib.sha256(self.data).digest()

    def get_blocks(self) -> typing.Iterator[typing.Tuple[int, bytes]]:
        """Returns an iterator (flash_offset, block_data) for every block. Call align() first."""
        block_offset = 0
        block_size = self.pico_info.max_data_size
        flash_offset = self.lower_bound
        for i in range((self.size + block_size - 1) // block_size):
            yield (flash_offset, self.data[block_offset : block_offset + block_size])
            block_offset += block_size
            flash_offset += block_size

    def align(self) -> None:
        """Ensure that the bounds of the data are aligned to the Pico Flash sector size, padding as needed."""

        # Get current bounds for the data
        block_size = self.pico_info.flash_sector_size
        all_blocks_start_offset = self.lower_bound
        all_blocks_end_offset = self.upper_bound

        # Add padding before (if needed)
        mask = block_size - 1
        pad_before = self.lower_bound & mask
        if pad_before > 0:
            self.add_block(self.lower_bound - pad_before, b"\xff" * pad_before)
        assert self.upper_bound == all_blocks_end_offset

        # Add padding after (if needed)
        pad_after = block_size - (self.upper_bound & mask)
        if pad_after < block_size:
            self.add_block(self.upper_bound, b"\xff" * pad_after)

        # Ensure that the data stayed in the same place but was padded appropriately
        assert self.lower_bound <= all_blocks_start_offset
        assert self.upper_bound >= all_blocks_end_offset
        assert (self.size % block_size) == 0
        assert (self.lower_bound % block_size) == 0

    def add_block(self, new_block_start_offset: int, new_block_data: bytes) -> None:
        """Add a new block to the file data."""

        # Get current bounds for the data
        all_blocks_start_offset = self.lower_bound
        all_blocks_end_offset = self.upper_bound
        new_block_end_offset = new_block_start_offset + len(new_block_data)

        if len(self.data) == 0:
            # First block special case
            self.data = new_block_data
            self.flash_offset = new_block_start_offset
            assert self.lower_bound == new_block_start_offset
            assert self.upper_bound == new_block_end_offset

        elif new_block_end_offset <= self.lower_bound:
            # New block appears before whatever we already have (with a gap of 0 or more bytes)
            gap = self.lower_bound - new_block_end_offset
            self.data = new_block_data + (b"\xff" * gap) + self.data
            self.flash_offset = new_block_start_offset
            assert self.lower_bound == new_block_start_offset
            assert self.upper_bound == all_blocks_end_offset

        elif new_block_start_offset < self.upper_bound:
            # New block appears within whatever we already have (overlapping at least 1 byte)
            raise LocalError(
                f"Blocks overlap in the input file: new block 0x{new_block_start_offset} "
                f".. 0x{new_block_end_offset} is within existing blocks "
                f"0x{self.lower_bound} .. 0x{self.upper_bound}")

        else:
            # New block appears after whatever we already have (with a gap of 0 or more bytes)
            gap = new_block_start_offset - self.upper_bound
            self.data = self.data + (b"\xff" * gap) + new_block_data
            assert self.lower_bound == all_blocks_start_offset
            assert self.upper_bound == new_block_end_offset

class BinaryFileReader(FileReader):
    def read(self, filename: Path) -> None:
        with open(filename, "rb") as fd:
            self.add_block(0, fd.read())

class UF2FileReader(FileReader):
    def read(self, filename: Path) -> None:
        with open(filename, "rb") as fd:
            uf2_block_size = 512
            uf2_max_data_size = 476
            wrong_family = False
            while True:
                raw_block = fd.read(uf2_block_size)
                if len(raw_block) == 0:
                    break # end of file
                if len(raw_block) != uf2_block_size:
                    raise LocalError(f"The UF2 file size must be a multiple of {uf2_block_size}")

                header_words = struct.unpack("<8I", raw_block[:32])
                footer_words = struct.unpack("<I", raw_block[-4:])
                if ((header_words[0] != 0x0A324655)
                or (header_words[1] != 0x9E5D5157)
                or (footer_words[0] != 0x0AB16F30)):
                    raise LocalError(f"The UF2 file has incorrect magic numbers")

                flags = header_words[2]
                if flags & 0x1001:
                    # Either: "no main flash flag" (0x1) or "file container flag" (0x1000) -> skip
                    continue

                if not (flags & 0x2000):
                    # Family ID is not set - skip
                    continue

                try:
                    block_family = Family(header_words[7])
                except ValueError:
                    block_family = Family.UNKNOWN

                if block_family != self.family:
                    # family ID is incorrect - skip
                    wrong_family = True
                    continue

                flash_offset = header_words[3] - self.pico_info.uf2_program_start_offset
                data_size = header_words[4]
                if data_size > uf2_max_data_size:
                    raise LocalError(f"The UF2 file has an incorrect data size")
                if ((flash_offset < 0)
                or ((flash_offset + data_size) >= self.pico_info.flash_size)):
                    # UF2 can only be used to load into Flash
                    raise LocalError(f"The UF2 file contains a block that is outside of Flash")

                self.add_block(flash_offset, raw_block[32:32 + data_size])

            if wrong_family and self.size == 0:
                raise LocalError(
                    f"The UF2 file doesn't contain any blocks with the expected family {self.family.name}")

async def do_load(client: Client, filename: Path,
                  load_offset: typing.Optional[int],
                  ota_mode: bool) -> typing.Tuple[int, FileReader]:

    # Sanity check for the file type
    file_type = get_file_type(filename)
    if file_type == FileType.WIFI_SETTINGS:
        raise LocalError(f"File '{filename}' appears to be a text file; " +
                          "this command requires a memory image file (.bin) or UF2 firmware file")
    elif file_type == FileType.ELF:
        raise LocalError(f"File '{filename}' appears to be an ELF file; " +
                          "this command requires a memory image file (.bin) or UF2 firmware file")
    elif file_type == FileType.NOT_FOUND:
        raise LocalError(f"File '{filename}' does not exist")

    # In OTA mode, this is the installation address, it is otherwise unused
    copy_to_offset = 0

    # Get the Pico info, in order to know enough about the existing program and Flash memory
    (result_data, result_value) = await client.run(ID_PICO_INFO_HANDLER)
    pico_info = PicoInfo(result_data)

    # Check various Pico Info properties which are expected to hold
    block_size = pico_info.flash_sector_size
    mask = block_size - 1
    (min_free_address, max_free_address) = pico_info.flash_reusable_range

    if not ((block_size <= pico_info.max_data_size)
    and ((block_size & mask) == 0)      # block size is a power of 2
    and (block_size >= 1)
    and (max_free_address > min_free_address)
    and ((min_free_address & mask) == 0) # multiple of block_size
    and ((max_free_address & mask) == 0)):
        raise RemoteError("Pico Info appears to contain inconsistent data")

    # Expected family for this device
    expected_family = pico_info.expected_family

    # Read the file
    file_reader: FileReader
    if file_type == FileType.UF2:
        file_reader = UF2FileReader(pico_info, expected_family)
    else:
        file_reader = BinaryFileReader(pico_info, expected_family)

    file_reader.read(filename)

    if file_reader.size == 0:
        raise LocalError(f"File '{filename}' is empty")

    # Determine the load offset (the Flash address where the new data should begin)
    min_offset = min_free_address
    if ota_mode:
        # In OTA mode the load offset will always be the end of the old program
        # or the new program (once installed), whichever is greater. Even when
        # loading a UF2 file. This is because the temporary storage must allow enough
        # space for the new program to be installed.
        assert load_offset is None
        file_reader.align()
        min_offset = max(min_free_address, file_reader.upper_bound)
        copy_to_offset = file_reader.lower_bound
        file_reader.set_lower_bound(min_offset)

    elif file_type == FileType.UF2:
        # For a UF2 file, when not doing an OTA update, we use the offsets in the file
        if load_offset is not None:
            raise LocalError(f"An offset cannot be specified when using an UF2 firmware file")
        file_reader.align()

    else:
        # Binary files require a load offset; we add this first, and then apply alignment
        if load_offset is None:
            raise LocalError(f"An offset must be specified when using a memory image file (.bin)")

        file_reader.set_lower_bound(load_offset + file_reader.lower_bound)
        file_reader.align()

    # Check whether data would be written to a valid place in Flash.
    # The user is not allowed to overwrite the current program, because although the
    # Flash writing procedure is in RAM, the TCP stack, WiFi driver and wifi-settings are not,
    # and as only max_data_size bytes can be uploaded at once, the program would be partially
    # overwritten while it was still running, which would be very bad.
    if ((file_reader.lower_bound < min_offset)
    or (file_reader.upper_bound > max_free_address)):
        raise LocalError(
            f"File '{filename}' cannot be loaded because data "
            f"would be written outside of the available Flash range "
            f"0x{min_offset:08x} .. 0x{max_free_address:08x}. Load range is "
            f"0x{file_reader.lower_bound:08x} .. 0x{file_reader.upper_bound:08x}.")

    total_size = file_reader.size
    print(f"Load {total_size} bytes:", flush=True)

    # Upload blocks
    copied_size = 0
    for (flash_offset, data) in file_reader.get_blocks():
        try:
            (result_data, result_value) = await client.run(ID_FLASH_WRITE_HANDLER,
                request_data=data, parameter=flash_offset)
        except BadHandlerError:
            raise NeedsMoreRemoteFeaturesError("ota" if ota_mode else "load") from None
        if result_value == PICO_ERROR_NOT_PERMITTED:
            raise RemoteError(
                "'Not Permitted' error received: this error comes from "
                "flash_safe_execute() and indicates that your firmware lacks support "
                "for safe multicore Flashing, which is needed for 'load' "
                "and 'ota' commands.")
        if result_value != 0:
            # Other error codes should not be seen, because the required validation
            # has already been done by the Python code in this function.
            raise PicoError(result_value)
        copied_size += len(data)
        percent = (copied_size * 100.0) / total_size
        print(f"\r {percent:1.0f}%", end="", flush=True)

    print(f"\rLoad ok, offset 0x{file_reader.lower_bound:08x}", flush=True)

    # Returned for the benefit of an OTA update
    return (copy_to_offset, file_reader)
