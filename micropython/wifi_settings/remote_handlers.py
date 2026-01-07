#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# This file declares built-in handlers for the remote update service for
# pico-wifi-settings.
#

from . import hostname

# Type-checking
try:
    import typing
    HandlerCallback1 = typing.Optional[typing.Callable[[int, bytes, int, typing.Any],
                                       typing.Tuple[bytes, int]]]
    # (msg_type, request_data_buffer, input_parameter, arg) -> (reply_data_buffer, return_value)
    HandlerCallback2 = typing.Optional[typing.Callable[[int, bytes, int, typing.Any], None]]
    # (msg_type, reply_data_buffer, return_value, arg) -> None
except ImportError:
    pass


def pico_info_handler(
        msg_type: int,
        request_data_buffer: bytes,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[bytes, int]:
    """For ID_PICO_INFO_HANDLER messages"""
    out: typing.List = []

    out.append("board_id=")
    out.append(hostname.get_board_id_hex())
    out.append("\n")

    return ("".join(out).encode(), 0)

def update_handler(
        msg_type: int,
        request_data_buffer: bytes,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[bytes, int]:
    """For ID_UPDATE_HANDLER messages"""
    return (b"", 0)

def update_reboot_handler1(
        msg_type: int,
        request_data_buffer: bytes,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[bytes, int]:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 1)"""
    return (b"", 0)

def update_reboot_handler2(
        msg_type: int,
        reply_data_buffer: bytes,
        return_value: int,
        arg: typing.Any) -> None:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 2)"""
