#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# This file declares built-in handlers for the remote update service for
# pico-wifi-settings.
#

from . import hostname, connection, configuration, remote
import machine # type: ignore

PICO_ERROR_INVALID_ARG = -5
PICO_ERROR_INVALID_DATA = -16

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

    if (request_data_buffer != b"") or (input_parameter != 0):
        return (b"", PICO_ERROR_INVALID_ARG)

    def add(key: str, value: str) -> None:
        out.append(key)
        out.append("=")
        out.append(value)
        out.append("\n")

    add("board_id", hostname.get_board_id_hex())
    add("name", hostname.get_hostname())
    add("ip", connection.get_ip())
    add("wifi_settings_version", configuration.WIFI_SETTINGS_VERSION_STRING)
    add("micropython", "1")

    return ("".join(out).encode(), 0)

def update_handler(
        msg_type: int,
        request_data_buffer: bytes,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[bytes, int]:
    """For ID_UPDATE_HANDLER messages"""

    if input_parameter != 0:
        return (b"", PICO_ERROR_INVALID_ARG)

    # Rewrite the settings file
    try:
        with open(configuration.WIFI_SETTINGS_FILE_NAME, "wb") as fd:
            fd.write(request_data_buffer)
    except Exception:
        return (b"", PICO_ERROR_INVALID_DATA)

    # Update information loaded from the file
    remote.update_secret()
    hostname.set_hostname()
    return (b"", len(request_data_buffer))

def update_reboot_handler1(
        msg_type: int,
        request_data_buffer: bytes,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[bytes, int]:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 1)"""
    return_value = update_handler(msg_type, request_data_buffer, input_parameter, arg)
    if return_value[1] == len(request_data_buffer):
        return (b"", 0) # success
    else:
        return return_value

def update_reboot_handler2(
        msg_type: int,
        reply_data_buffer: bytes,
        return_value: int,
        arg: typing.Any) -> None:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 2)"""
    # This part will actually do the reboot if there is no error from stage 1
    if return_value == 0:
        machine.reset()
