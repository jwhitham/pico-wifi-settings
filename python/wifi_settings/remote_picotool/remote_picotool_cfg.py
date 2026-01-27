"""
Represents a remote_picotool configuration based on a configuration file and parameters.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..exceptions import *
from .. import typing_shim as typing
from ..key_value_store import KeyValueStore
from ..update_secret_hash import update_secret_hash
from ..file_type import FileType, get_file_type
from ..configuration import PORT_NUMBER, REMOTE_PICOTOOL_CFG_NAME

from pathlib import Path

import argparse
import os


class RemotePicotoolCfg(KeyValueStore):
    """This represents a remote_picotool configuration, from a file, or parameters, or both."""

    def __init__(self, args: typing.Optional[argparse.Namespace] = None) -> None:
        """Get the remote_picotool configuration contents.

        This may be loaded from a file. The file is named remote_picotool.cfg and
        may specify the update_secret, the board ID and the IP address,
        avoiding any need to specify these settings when running remote_picotool.

        In particular you can create a remote_picotool.cfg file in the root
        of your Git repository and it will be used whenever you run remote_picotool
        within the Git repository.

        The following places are searched for the file, in this order:
         - Use the command-line option `--config` (if provided)
         - Use the environment variable `PICO_REMOTE_PICOTOOL_CFG` (if set)
         - Use the contents of file `remote_picotool.cfg` in the current directory (if it exists)
         - Use the contents of file `remote_picotool.cfg` in any parent directory (if it exists)
         - Use the contents of file `$APPDATA/remote_picotool.cfg` (if it exists)
         - Use the contents of file `$XDG_CONFIG_HOME/remote_picotool.cfg` (if it exists)
         - Use the contents of file `~/.config/remote_picotool.cfg` (if it exists)

        A priority order is applied for all parameters:
         - The command-line option overrides everything
         - Special case 1: an environment variable is used if defined (e.g. PICO_ID for --board-id)
         - Special case 2: update_secret can be loaded from a wifi-settings file if one is specified
         - The value is taken from the the `remote_picotool.cfg` file
         - A default value is used e.g. 1404 for --port
        """
        KeyValueStore.__init__(self, b"")

        # Use the command-line parameters provided by the caller, if any
        # The static method add_config_options() will add the options to an ArgumentParser object
        if args is None:
            args = argparse.Namespace()
        self.args = args

        # Get the config file location from the environment or from the command line if possible
        self.override_from_environment("config", "PICO_REMOTE_PICOTOOL_CFG")
        self.override_from_args("config")

        # If the config file location is not known then search current directory and parents
        if not self.config:
            ancestor_dir = Path.cwd()
            while ancestor_dir != ancestor_dir.parent:
                config_file = ancestor_dir / REMOTE_PICOTOOL_CFG_NAME
                if config_file.is_file():
                    self.set("config", str(config_file))
                    break
                ancestor_dir = ancestor_dir.parent

        # If the config file location is not known then search home directory locations
        if not self.config:
            config_dir = (os.getenv("APPDATA", "") or os.getenv("XDG_CONFIG_HOME", "")
                                 or str(Path.home() / ".config"))
            if config_dir:
                config_file = Path(config_dir) / REMOTE_PICOTOOL_CFG_NAME
                if config_file.is_file():
                    self.set("config", str(config_file))

        # Set defaults
        self.set("port", str(PORT_NUMBER))
        self.set("search_timeout", "0.5")

        # Read file contents if any file was found
        # They are prepended so that new settings override whatever was found so far
        if self.config:
            self.contents = Path(self.config).read_bytes() + b"\n" + self.contents

        # Special case 1: Override some settings from environment variables (if specified)
        self.override_from_environment("update_secret", "PICO_UPDATE_SECRET")
        self.override_from_environment("board_address", "PICO_ADDRESS")
        self.override_from_environment("board_id", "PICO_ID")

        # Special case 2: The update secret might also be loaded from a wifi-settings file
        if (not self.update_secret_text
        and hasattr(self.args, "filename")
        and (get_file_type(self.args.filename) == FileType.WIFI_SETTINGS)):
            self.set("update_secret", WifiSettingsFile(self.args.filename.read_bytes()).update_secret_text)

        # Override all settings from the command line options (if specified)
        self.override_from_args("port")
        self.override_from_args("search_timeout")
        self.override_from_args("search_interface")
        self.override_from_args("update_secret")
        self.override_from_args("board_address")
        self.override_from_args("board_id")

    @staticmethod
    def add_config_options(parser: argparse.ArgumentParser) -> None:
        """Add command-line options to a parser.

        This method can be used to create a tool which accepts the same
        configuration options as remote_picotool but has custom commands."""
        parser.add_argument("--port",
            type=int,
            metavar="N",
            help="Port number")
        parser.add_argument("--search-timeout",
            type=float,
            metavar="SECONDS",
            help="Timeout for search when the target address is not specified")
        parser.add_argument("--search-interface",
            type=str,
            metavar="A.B.C.D",
            help="IP address of local interface to be used for search when the target address is not specified")
        parser.add_argument("--update-secret", "--secret",
            type=str,
            metavar="PASSPHRASE",
            help="Shared secret (configured as update_secret in the WiFi settings file)")
        parser.add_argument("--board-address", "--address",
            type=str,
            metavar="A.B.C.D",
            help="Target address for Pico W (IP or hostname)")
        parser.add_argument("--board-id", "--id",
            type=str,
            metavar="ID",
            help="Target board ID (may be partial)")
        parser.add_argument("--config",
            type=Path,
            metavar="CFG",
            help="Configuration file for remote_picotool containing one or more of "
                 "the preceding options, e.g. board_id=... or update_secret=...")

    def override_from_environment(self, key: str, env_var_name: str) -> None:
        """Override an option setting from an environment variable, if the env var exists."""
        value = os.getenv(key, "")
        if value:
            self.set(key, value)

    def override_from_args(self, key: str) -> None:
        """Override an option setting from a command-line option, if the option was used."""
        if hasattr(self.args, key):
            value = getattr(self.args, key, None)
            if value is not None:
                self.set(key, str(value))

    @property
    def config(self) -> str:
        """Location of remote_picotool.cfg file (if any).

        This is:
         - the --config option on the command line
         - the environment variable PICO_REMOTE_PICOTOOL_CFG
         - various search locations on disk
        """
        return self.get_str("config")

    @property
    def port(self) -> int:
        """Port number for connecting to Pico W.

        This is:
         - the port= option in remote_picotool.cfg
         - the --port option on the command line
        """
        return self.get_int("port")

    @property
    def search_timeout(self) -> float:
        """Timeout for searching for Pico W (seconds).

        This is:
         - the search_timeout= option in remote_picotool.cfg
         - the --search-timeout option on the command line
        """
        return self.get_float("search_timeout")

    @property
    def search_interface(self) -> str:
        """IPv4 address of interface for searching for Pico W.

        This is:
         - the search_interface= option in remote_picotool.cfg
         - the --search-interface option on the command line
        """
        return self.get_str("search_interface")

    @property
    def update_secret_text(self) -> str:
        """Update secret as text.

        This is:
         - the update_secret= option in remote_picotool.cfg (or the wifi-settings file)
         - the --update-secret or --secret option on the command line
         - the environment variable PICO_UPDATE_SECRET
        """
        return self.get_str("update_secret")

    @property
    def board_address(self) -> str:
        """IPv4 address of Pico W.

        This is:
         - the board_address= option in remote_picotool.cfg
         - the --board-address or --address option on the command line
         - the environment variable PICO_ADDRESS
        """
        return self.get_str("board_address")

    @property
    def board_id(self) -> str:
        """Board ID of Pico W.

        This is:
         - the board_id= option in remote_picotool.cfg
         - the --board-id or --id option on the command line
         - the environment variable PICO_ID
        """
        return self.get_str("board_id")

    @property
    def update_secret_hash(self) -> bytes:
        """Turn the secret provided by the user into a 32-byte hash.

        This is derived from:
         - the update_secret= option in remote_picotool.cfg (or the wifi-settings file)
         - the --update-secret or --secret option on the command line
         - the environment variable PICO_UPDATE_SECRET
        """

        if not self.update_secret_text:
            raise NoSecretError("No update_secret is available for the client (use --secret)")

        return update_secret_hash(self.update_secret_text)

class WifiSettingsFile(KeyValueStore):
    """This represents information in a wifi-settings file."""

    @property
    def update_secret_text(self) -> str:
        """Update secret as text."""
        return self.get_str("update_secret")
