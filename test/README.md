# Tests

These tests should be executed with pytest:
```
    python -m pytest .
```
They've only been used on Linux. They require at least:

 - Recent Python 3.x version (recommend 3.10)
 - `pytest`, `pyaes` and `mypy` Python modules installed
 - Pico SDK, either installed as `pico-sdk` in the directory above the root,
   or in the `$PICO_SDK_PATH` directory.
 - Pico SDK is able to build applications that use WiFi.
 - GCC tools for local builds (unit tests run as native binaries).

The tests do not require Pico hardware.

# Release tool

This is a build tool for the setup app and examples
which also provides estimates of the size difference
that results from integrating pico-wifi-settings.
