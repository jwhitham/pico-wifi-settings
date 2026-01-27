"""
AES interface for pico-wifi-settings Python code.

In order to allow different implementations of AES to be used,
this module abstracts an AES implementation into a class which
accepts a key and provides encrypt/decrypt methods.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from . import typing_shim as typing

AES_BLOCK_SIZE = 16
AES_IV = b"\x00" * AES_BLOCK_SIZE

class AbstractAES256CBCFactory:
    def __init__(self, key: bytes) -> None:
        pass

    def encrypt(self, block: bytes) -> bytes:
        return AES_IV

    def decrypt(self, block: bytes) -> bytes:
        return AES_IV

AES256CBCFactory: typing.Type[AbstractAES256CBCFactory]

try:
    # Micropython crypto module
    import cryptolib # type: ignore

    class MicropythonAES256CBCFactory(cryptolib.aes, AbstractAES256CBCFactory):
        def __init__(self, key: bytes) -> None:
            # Magic number for CBC mode is 2
            # see https://github.com/micropython/micropython/blob/master/docs/library/cryptolib.rst
            cryptolib.aes.__init__(self, key, 2, AES_IV)

    AES256CBCFactory = MicropythonAES256CBCFactory

except ImportError:
    try:
        # pyaes module
        import pyaes # type: ignore

        class PyaesAES256CBCFactory(pyaes.aes.AESModeOfOperationCBC, AbstractAES256CBCFactory):
            def __init__(self, key: bytes) -> None:
                pyaes.aes.AESModeOfOperationCBC.__init__(self, key=key, iv=AES_IV)

        AES256CBCFactory = PyaesAES256CBCFactory

    except ImportError:
        print("The pyaes module is required; please install it with 'pip install pyaes' or 'apt install python3-pyaes'")
        exit(1)
