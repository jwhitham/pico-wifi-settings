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
import sys

PICO_ERROR_INVALID_ARG = -5
PICO_ERROR_INVALID_DATA = -16

# Type-checking
try:
    import typing
    # Callback 1:
    # Call parameters: (msg_type, data_buffer, input_data_size, input_parameter, arg)
    # Return value: (output_data_size, result_value)
    HandlerCallback1 = typing.Optional[typing.Callable[[int, bytearray, int, int, typing.Any], typing.Tuple[int, int]]]
    # Callback 2:
    # Call parameters: (msg_type, data_buffer, output_data_size, result_value, arg)
    # Return value: None
    HandlerCallback2 = typing.Optional[typing.Callable[[int, bytearray, int, int, typing.Any], None]]
except ImportError:
    pass


def pico_info_handler(
        msg_type: int,
        data_buffer: bytearray,
        input_data_size: int,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[int, int]:
    """For ID_PICO_INFO_HANDLER messages"""
    out: typing.List = []

    if (input_data_size != 0) or (input_parameter != 0):
        return (0, PICO_ERROR_INVALID_ARG)

    def add(key: str, value: typing.Union[str, int]) -> None:
        out.append(key)
        out.append("=")
        out.append(str(value))
        out.append("\n")

    # board id
    add("board_id", hostname.get_board_id_hex())

    # network info
    add("name", hostname.get_hostname())
    add("ip", connection.get_ip())

    # program info
    add("wifi_settings_version", configuration.WIFI_SETTINGS_VERSION_STRING)
    add("id_last_user_handler", remote.ID_LAST_USER_HANDLER)
    add("max_data_size", remote.MAX_DATA_SIZE)
    add("implementation", "MicroPython")
    add("sdk_version", sys.version)

    # Output
    out_bytes = "".join(out).encode()
    out_size = min(len(data_buffer), len(out_bytes))
    data_buffer[:out_size] = out_bytes
    return (out_size, 0)

def update_handler(
        msg_type: int,
        data_buffer: bytearray,
        input_data_size: int,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[int, int]:
    """For ID_UPDATE_HANDLER messages"""

    if input_parameter != 0:
        return (0, PICO_ERROR_INVALID_ARG)

    # Rewrite the settings file
    try:
        with open(configuration.WIFI_SETTINGS_FILE_NAME, "wb") as fd:
            fd.write(data_buffer[:input_data_size])
    except Exception:
        return (0, PICO_ERROR_INVALID_DATA)

    # Update information loaded from the file
    remote.update_secret()
    hostname.set_hostname()
    return (0, input_data_size)

def update_reboot_handler1(
        msg_type: int,
        data_buffer: bytearray,
        input_data_size: int,
        input_parameter: int,
        arg: typing.Any) -> typing.Tuple[int, int]:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 1)"""
    return_value = update_handler(msg_type, data_buffer, input_data_size, input_parameter, arg)
    if (0, input_data_size) == return_value:
        return (0, 0) # success - go to stage 2
    else:
        return return_value

def update_reboot_handler2(
        msg_type: int,
        data_buffer: bytearray,
        output_data_size: int,
        result_value: int,
        arg: typing.Any) -> None:
    """For ID_UPDATE_REBOOT_HANDLER messages (stage 2)"""
    # This part will actually do the reboot if there is no error from stage 1
    if (output_data_size == 0) and (result_value == 0):
        machine.reset()
