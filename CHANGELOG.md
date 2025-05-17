# CHANGELOG

This documents important changes in the project.

## v0.2.1

- Support mbedtls v3 as used in pico-sdk 'develop'
- Adjust build settings to avoid imposing -Werror
- Add functions to access SSID and IP address directly
- Update documentation with better link to picotool
- Weak symbol for `wifi_settings_get_value_for_key`

## v0.2.0

- Support for wifi-settings file at a user-defined address:
  - `-DWIFI_SETTINGS_FILE_ADDRESS=0x...` can be used to set the address at build time
  - The setup app searches for the wifi-settings file and allows the user to reconfigure the location
- The default address of the wifi-settings file changes to 16kb before the end of Flash
  - i.e. 0x101fc000 on Pico and 0x103fc000 on Pico 2

## v0.1.4

- Create subset library, wifi\_settings\_connect.

## v0.1.3

- Add UF2 support to remote\_picotool for the `load` and `ota` commands
- Add an improved integration test for remote\_picotool
- Fix bug preventing use of OTA feature on CPU 1

## v0.1.2

- Add Bazel build support
- Fix various minor issues with documentation
- Fix support for some older C compilers

## v0.1.1

First public version.
