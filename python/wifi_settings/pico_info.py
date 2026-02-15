"""
PicoInfo representation.

The PicoInfo object contains information from ID_PICO_INFO_HANDLER
about the remote device hardware such as the memory size, and also
information about the firmware that's currently installed.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .handler_ids import ID_PICO_INFO_HANDLER
from .key_value_store import KeyValueStore, FlashRange

import enum

class Family(enum.Enum):
    UNKNOWN = 0
    RP2040 = 0xe48bff56 # "Raspberry Pi RP2040"
    RP2XXX_ABSOLUTE = 0xe48bff57 # "Raspberry Pi Microcontrollers: Absolute (unpartitioned) download"
    RP2XXX_DATA = 0xe48bff58 # "Raspberry Pi Microcontrollers: Data partition download"
    RP2350_ARM_S = 0xe48bff59 # "Raspberry Pi RP2350, Secure Arm image"
    RP2350_RISCV = 0xe48bff5a # "Raspberry Pi RP2350, RISC-V image"
    RP2350_ARM_NS = 0xe48bff5b # "Raspberry Pi RP2350, Non-secure Arm image"

class PicoInfo(KeyValueStore):
    """This represents information from ID_PICO_INFO_HANDLER."""

    @property
    def sysinfo_chip_id(self) -> int:
        return self.get_int("sysinfo_chip_id")

    @property
    def flash_sector_size(self) -> int:
        return self.get_int("flash_sector_size")

    @property
    def logical_offset(self) -> int:
        """Return the absolute unremapped address of the first byte of Flash memory.

        This is the absolute address that a program running on the Pico CPU would use
        to access the first byte of Flash, bypassing any remapping (partitioning)."""
        return self.get_int("logical_offset")

    @property
    def uf2_program_start_offset(self) -> int:
        """Return the potentially-remapped address of the first byte of Flash memory.

        This is the address that would be used inside a UF2 file to refer to the beginning
        of Flash. It is constant. The physical address might be very different (partitioning)."""
        return 0x10000000

    @property
    def flash_size(self) -> int:
        (start, end) = self.flash_range
        return end - start

    @property
    def flash_range(self) -> FlashRange:
        return self.get_range("flash_all")

    @property
    def flash_reusable_range(self) -> FlashRange:
        return self.get_range("flash_reusable")

    @property
    def flash_wifi_settings_file_range(self) -> FlashRange:
        return self.get_range("flash_wifi_settings_file")

    @property
    def flash_program_range(self) -> FlashRange:
        return self.get_range("flash_program")

    @property
    def max_data_size(self) -> int:
        return self.get_int("max_data_size")

    @property
    def board_id(self) -> str:
        return self.get_str("board_id")

    @property
    def name(self) -> str:
        return self.get_str("name")

    @property
    def implementation(self) -> str:
        return self.get_str("implementation")

    @property
    def revision(self) -> int:
        return self.sysinfo_chip_id >> 28

    @property
    def part_number(self) -> int:
        return (self.sysinfo_chip_id >> 12) & 0xffff

    @property
    def manufacturer_id(self) -> int:
        return self.sysinfo_chip_id & 0xffe

    @property
    def type_name(self) -> str:
        if self.manufacturer_id == 0x926:
            return {
                2: "RP2040",
                4: "RP2350",
            }.get(self.part_number, "<not known>")
        else:
            return "<not RPi>"

    @property
    def expected_family(self) -> "Family":
        return {
            "RP2040": Family.RP2040,
            "RP2350": Family.RP2350_ARM_S,
        }.get(self.type_name, Family.UNKNOWN)
