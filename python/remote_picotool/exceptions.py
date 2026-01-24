"""
Exceptions that may be raised by the pico-wifi-settings Python client.

Some are subclasses of LocalError and represent local failures or
connection errors, while others represent failures reported by the
server (RemoteError).

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""


class RemoteError(Exception):
    """Base for all errors relating to issues with the remote system."""
    pass

class LocalError(Exception):
    """Base for all errors relating to local issues e.g. incorrect parameters."""
    pass

class TooLargeError(LocalError):
    """The requested data size is too large due to the MAX_DATA_SIZE limit on the remote."""
    pass

class PicoError(RemoteError):
    """Error with a code from src/common/pico_base_headers/include/pico/error.h"""
    def __init__(self, code: int) -> None:
        RemoteError.__init__(self, "Pico error code {} received: {}".format(
            code, {
            -1: "PICO_ERROR_GENERIC",
            -2: "PICO_ERROR_TIMEOUT",
            -3: "PICO_ERROR_NO_DATA",
            -4: "PICO_ERROR_NOT_PERMITTED",
            -5: "PICO_ERROR_INVALID_ARG",
            -6: "PICO_ERROR_IO",
            -7: "PICO_ERROR_BADAUTH",
            -8: "PICO_ERROR_CONNECT_FAILED",
            -9: "PICO_ERROR_INSUFFICIENT_RESOURCES",
            -10: "PICO_ERROR_INVALID_ADDRESS",
            -11: "PICO_ERROR_BAD_ALIGNMENT",
            -12: "PICO_ERROR_INVALID_STATE",
            -13: "PICO_ERROR_BUFFER_TOO_SMALL",
            -14: "PICO_ERROR_PRECONDITION_NOT_MET",
            -15: "PICO_ERROR_MODIFIED_DATA",
            -16: "PICO_ERROR_INVALID_DATA",
            -17: "PICO_ERROR_NOT_FOUND",
            -18: "PICO_ERROR_UNSUPPORTED_MODIFICATION",
            -19: "PICO_ERROR_LOCK_REQUIRED",
            -20: "PICO_ERROR_VERSION_MISMATCH",
            -21: "PICO_ERROR_RESOURCE_IN_USE",
            }.get(code, "unknown")))
        self.code = code

class BadMessageError(RemoteError):
    """Indicates an invalid request was received during the
    unencrypted communication stage."""
    def __init__(self, received_msg_type: int, expected_msg_type: int) -> None:
        RemoteError.__init__(self)
        self.received_msg_type = received_msg_type
        self.expected_msg_type = expected_msg_type

    def __str__(self) -> str:
        return (f"BadMessageError(received {self.received_msg_type} " +
                f"expected {self.expected_msg_type})")

class BadVersionError(RemoteError):
    """Indicates an invalid version number was received during the
    unencrypted communication stage."""
    def __init__(self, version: int) -> None:
        RemoteError.__init__(self)
        self.version = version

    def __str__(self) -> str:
        return f"BadVersionError({self.version})"

class AuthenticationError(RemoteError):
    """Indicates that the client and server don't share the same update secret."""
    def __str__(self) -> str:
        return ("AuthenticationError: the given --secret "
            "does not match the update_secret on the board")

class CorruptedMessageError(RemoteError):
    """Indicates corruption in the encrypted communication stage."""
    def __init__(self, hint: str) -> None:
        RemoteError.__init__(self)
        self.hint = hint

    def __str__(self) -> str:
        return f"CorruptedMessageError({self.hint})"

class BadParameterError(RemoteError):
    """Indicates parameters for the handler are invalid."""
    def __str__(self) -> str:
        return "BadParameterError()"

class HandlerFailedError(RemoteError):
    """Indicates handler returned CALLBACK_FAILURE_ERROR."""
    def __str__(self) -> str:
        return "HandlerFailedError()"

class BadHandlerError(RemoteError):
    """Indicates the requested handler does not exist."""
    def __str__(self) -> str:
        return "BadHandlerError()"

class UnknownError(RemoteError):
    """Indicates the requested handler failed in some unknown way."""
    def __str__(self) -> str:
        return "UnknownError()"

class NeedsMoreRemoteFeaturesError(RemoteError):
    """Indicates that the remote does not have the requested feature."""
    def __init__(self, command: str) -> None:
        RemoteError.__init__(self,
            f"The board firmware does not support the '{command}' command "
            + "and must be recompiled with memory access features "
            + "(e.g. use 'cmake -DWIFI_SETTINGS_REMOTE=2')")

class NoSecretError(RemoteError):
    """This error is generated when the remote does not have any update_secret configured."""
    pass
