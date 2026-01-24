"""
Open a network connection to a device running pico-wifi-settings firmware.

The connection can be made using an IP address or using a board ID; if a
board ID is used then a search process involving a UDP broadcast will be used.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from .remote_picotool_cfg import RemotePicotoolCfg
from .asyncio_board_id import get_pico_address_for_board_id

from asyncio import StreamReader, StreamWriter

import asyncio 
import typing

async def get_pico_connection(config: RemotePicotoolCfg) -> typing.Tuple[StreamReader, StreamWriter]:
    """Connect to a Pico, determining the board ID or address from the configuration.

    There are many ways to specify the board ID or address. For example,
     - Use `--address <x.x.x.x>` to provide an IP address or hostname.
     - Use `--id <x>` to provide all or part of the board ID (see below).
     - Use the environment variable `PICO_ADDRESS` to provide an IP address or hostname.
     - Use the environment variable `PICO_ID` to provide all or part of the board ID.
     - Use `board_address=<x.x.x.x>in the remote_picotool.cfg file.
     - Use `board_id=<x>` in the remote_picotool.cfg file.
    """

    if config.board_address:
        return await get_pico_connection_for_address(config.board_address, config)

    if config.board_id:
        return await get_pico_connection_for_board_id(config.board_id, config)

    # No address provided, no ID provided? Hopefully there is only one board on the network!
    return await get_pico_connection_for_board_id(None, config)

async def get_pico_connection_for_address(
        address: str,
        config: RemotePicotoolCfg) -> typing.Tuple[StreamReader, StreamWriter]:
    """Connect to a Pico at a specified address with a port from the command line."""
    return await asyncio.open_connection(address, config.port)

async def get_pico_connection_for_board_id(
        board_id: typing.Optional[str],
        config: RemotePicotoolCfg) -> typing.Tuple[StreamReader, StreamWriter]:
    """Connect to a Pico at a specified address with a port from the command line."""
    address = await get_pico_address_for_board_id(board_id, config)
    return await get_pico_connection_for_address(address, config)

