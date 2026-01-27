"""
Remote update client for wifi-settings. Pico firmware built with the wifi-settings
library, an 'update_secret' and the -DWIFI_SETTINGS_REMOTE build option can be
remotely updated using this program. Run with --help for instructions,
or visit https://github.com/jwhitham/pico-wifi-settings

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..exceptions import *
from .remote_picotool_cfg import RemotePicotoolCfg
from . import subcommands
from .subcommands import UpdateRebootMode

from pathlib import Path

import argparse
import sys

URL = "https://github.com/jwhitham/pico-wifi-settings"


def add_wifi_settings_file_argument(parser_info: argparse.ArgumentParser) -> None:
    parser_info.add_argument("filename",
        type=Path,
        metavar="FILE",
        help="WiFi settings file")

def add_firmware_file_argument(parser_info: argparse.ArgumentParser) -> None:
    parser_info.add_argument("filename",
        type=Path,
        metavar="FILE.bin",
        help="Memory image file (always in .bin format)")

def main() -> None:
    parser = argparse.ArgumentParser("remote_picotool",
        description="Pico W devices can only be controlled by remote_picotool if they "
            "are running firmware with wifi-settings and an update_secret is configured. "
            "Subcommands marked with [*] also require building with -DWIFI_SETTINGS_REMOTE=2. "
            "See " + URL + " for instructions.")

    RemotePicotoolCfg.add_config_options(parser)

    subparser = parser.add_subparsers(required=True,
            description="Use remote_picotool <subcommand> --help for more details:")

    parser_info = subparser.add_parser("info",
        help="Print information about the Pico W and the current configuration")
    parser_info.set_defaults(func=subcommands.subcommand_info)
    parser_info.add_argument("--raw",
        action="store_true",
        help="Dump raw data from the board")

    parser_update = subparser.add_parser("update",
        help="Update the WiFi settings file on the Pico W")
    add_wifi_settings_file_argument(parser_update)
    parser_update.set_defaults(func=subcommands.subcommand_update_reboot)
    parser_update.set_defaults(mode=UpdateRebootMode.UPDATE)

    parser_update_reboot = subparser.add_parser("update_reboot",
        help="Update the WiFi settings file on the Pico W and then immediately reboot")
    add_wifi_settings_file_argument(parser_update_reboot)
    parser_update_reboot.set_defaults(func=subcommands.subcommand_update_reboot)
    parser_update_reboot.set_defaults(mode=UpdateRebootMode.UPDATE_REBOOT)

    parser_reboot = subparser.add_parser("reboot",
        help="Reboot the Pico W into user firmware")
    parser_reboot.set_defaults(func=subcommands.subcommand_update_reboot)
    parser_reboot.set_defaults(mode=UpdateRebootMode.REBOOT)

    parser_bootloader = subparser.add_parser("reboot_bootloader",
        help="Reboot the Pico W into the ROM bootloader " +
            "(as if BOOTSEL were held down during power on) [*]")
    parser_bootloader.set_defaults(func=subcommands.subcommand_update_reboot)
    parser_bootloader.set_defaults(mode=UpdateRebootMode.REBOOT_BOOTLOADER)

    parser_save = subparser.add_parser("save", help="Save memory to a file [*]")
    parser_save.add_argument("-a", "--all", action="store_true", help="Save all of Flash memory")
    parser_save.add_argument("-p", "--program", action="store_true", help="Save the installed program only (this is the default)")
    parser_save.add_argument("-r", "--range", nargs=2,
            metavar="LOGICAL", type=lambda s: int(s, 0),
            help="Save a range of memory. These are logical addresses, "
                "i.e. addresses as seen by the program. Only SRAM and Flash "
                "addresses can be accessed. For Pico 2 with partitions, "
                "use the 0x1c...... range to access untranslated Flash "
                "addresses outside of the current partition (e.g. "
                "the wifi-settings file) and 0x10...... for translated "
                "addresses in the current partition.")
    add_firmware_file_argument(parser_save)
    parser_save.set_defaults(func=subcommands.subcommand_save)

    parser_load = subparser.add_parser("load", help="Load Flash memory from a file [*]")
    parser_load.add_argument("-o", "--offset",
            metavar="FLASH", type=lambda s: int(s, 0),
            help="Load offset for binary files. This is a physical address in Flash, "
                "i.e. address 0 is the start of Flash.")
    add_firmware_file_argument(parser_load)
    parser_load.set_defaults(func=subcommands.subcommand_load)

    parser_ota = subparser.add_parser("ota", help="Perform over-the-air (OTA) firmware update [*]")
    add_firmware_file_argument(parser_ota)
    parser_ota.set_defaults(func=subcommands.subcommand_ota)

    parser_list = subparser.add_parser("list", help="List all Pico W devices matching the --id search criteria")
    parser_list.set_defaults(func=subcommands.subcommand_list)

    args = parser.parse_args(sys.argv[1:] or ["--help"])
    try:
        args.func(args)
    except RemoteError as e:
        print("Remote error:", str(e))
        sys.exit(1)
    except LocalError as e:
        print("Error:", str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)

if __name__ == "__main__":
    main()
