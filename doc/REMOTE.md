# Remote updates

When pico-wifi-settings is built with default options, it is possible to remotely
update the [WiFi settings file](SETTINGS_FILE.md).

This requires the following:

 - The WiFi settings file must already exist, and must already contain
   the settings needed to connect to WiFi.
 - The WiFi settings file must contain an `update_secret`.
 - wifi\_settings must have been [integrated with your Pico application](INTEGRATION.md).
 - A PC, server, Raspberry Pi or other computer capable of running the
   [remote\_picotool](../remote_picotool) program:
    - You need to install the `pyaes` Python module: 
      `pip install pyaes` or `apt install python3-pyaes`
    - Python version >= 3.10 is recommended 
 - The Pico must be powered on!
 - The Pico should be connected to the same WiFi network
   as the PC or server that will send the update.

# CMake flags

CMake build options control whether remote update features are enabled:

 - `cmake -DWIFI_SETTINGS_REMOTE=0` will disable all remote update features.
   This will reduce your application binary size.
 - `cmake -DWIFI_SETTINGS_REMOTE=1` is the default setting. It allows some
   basic remote update commands (`info`, `update`, `update_reboot`, `reboot`).
   These commands only allow you to replace the WiFi settings file and reboot the
   Pico remotely.
 - `cmake -DWIFI_SETTINGS_REMOTE=2` is the maximum setting. This enables commands
   for remote access to Pico memory (RAM and Flash). These powerful commands
   allow you to replace all of the Pico software "over the air" (OTA)
   without any physical access to the hardware.

There are [Bazel equivalents](/doc/BAZEL.md) of these options for Bazel projects.

# Update Secret

`update_secret` is a "shared secret" stored in the WiFi settings file and
also given to the [remote\_picotool](../remote_picotool) program. All remote
access to the Pico requires the correct update secret.

The update secret should be a password, passphrase or random alphanumeric text.
You could generate a suitable random update secret using a tool such as
`openssl rand -base64 33`. Here is an example with a very weak password which
will be used throughout this document:
```
update_secret=hunter2
```

# Testing remote access

To test remote access to a Pico application, such as
the [setup app](SETUP_APP.md), run [remote\_picotool](../remote_picotool) with
the `info` parameter and the update secret:
```
python remote_picotool --secret hunter2 info
```
This will automatically search for your Pico using a UDP broadcast. If successful,
it will print out some information about your Pico.

# Updating the WiFi settings file by WiFi

To send an updated WiFi settings file, run [remote\_picotool](../remote_picotool) with
the IP address and the updated WiFi settings file, for example:
```
python remote_picotool --secret hunter2 update_reboot mywifisettings.txt
```
The file will be updated on the Pico and then the Pico will reboot (returning
to your Pico application with the updated WiFi settings file).

# More than one Pico on the network

If you have more than one Pico on your WiFi network, you will need to indicate
which one should be updated. This is done using a board ID or IP address,
and there are several methods for specifying these. Here are two examples:
```
python remote_picotool --secret hunter2 --id 1718 info
python remote_picotool --secret hunter2 --address 192.168.0.200 info
```

## Board IDs, --id and the list command

To see a list of all devices on your network, you can use the `list` command
to print the results of a UDP broadcast which triggers a response
from all Pico devices with a pico-wifi-settings application:
```
python remote_picotool list
```
The list shows the board ID and IP address of each Pico. You can use all or part
of the board ID with the `--id` option in order to select a particular device;
if a partial ID is used, it can be any substring. For example, `1718` and `854D` will
both match `E6614854D3B51718`.

Each board ID is unique to a Pico, and can also be printed using 
[picotool](https://github.com/raspberrypi/pico-sdk-tools/releases)
with `picotool info -d` when the
Pico is connected by USB (it appears as "flash id" or "chipid" depending on the
Pico version). The board ID is also shown when running the [setup app](SETUP_APP.md)
and will be printed out by the `remote_picotool info` command.

## The --address option

Using the address option will cause
remote\_picotool to connect directly to the IP address you provide.
This may be preferable to a UDP broadcast, which will only work if your
development PC and Pico are on the same network.

# Providing the update secret

remote\_picotool requires the update secret for all commands except for `list`.
The update secret can be provided in several ways:

 - Use `--secret` to provide the update secret on the command line.
 - Use the environment variable `PICO_UPDATE_SECRET`.
 - Use a `remote_picotool.cfg` file (see below).
 - Use the `update_secret=` line in the WiFi settings file that you provide
   when running an `update_reboot` or `update` command.

If you wish to change the `update_secret=` value, you can do so by (1) putting the
new value in the wifi-settings file, and (2) using the `--secret` option to provide the
old value when running the `update_reboot` command.

# remote\_picotool.cfg

If you work with several different Pico W projects, it can be difficult
to manage all of the board IDs and update secrets. Creating a `remote_picotool.cfg`
file within each project can help with this.
It is a text file similar to a wifi-settings file which is read
by remote\_picotool on startup. It contains Pico-specific values for configuration
options, for example:
```
update_secret=hunter2
board_id=E6614854D3B51718
```
The following keys can be used in the file:

 - `update_secret`
 - `board_id`
 - `board_address`
 - `port`
 - `search_timeout`
 - `search_interface`

The file should be created in the root of your source tree (e.g. Git repository).
Whenever you run remote\_picotool, it will search all parent directories for
remote\_picotool.cfg and load settings from the first file that it finds.
In this way, each of your Pico projects can
have its own configuration for remote access, and the remote\_picotool command
can be used to update the wifi-settings file and the firmware via WiFi without
any command-line options.

Command-line options and environment
variables will override remote\_picotool.cfg. If you are using Git,
consider adding remote\_picotool.cfg to `.gitignore` in order to
avoid committing your `update_secret`.

You can also create a global remote\_picotool.cfg file in the following locations:

 - `$APPDATA/remote_picotool.cfg`
 - `$XDG_CONFIG_HOME/remote_picotool.cfg`
 - `~/.config/remote_picotool.cfg`

This will be used if no other remote\_picotool.cfg file can be found.

# Over-the-air (OTA) firmware updates

remote\_picotool can be used to install OTA updates. This feature allows
you to upgrade your Pico application via WiFi without a USB connection. The requirements
are as follows:

 - You must build your application with the CMake option `-DWIFI_SETTINGS_REMOTE=2`.
 - The WiFi settings file must contain an `update_secret`.
 - Both versions of your application (the existing version and the new version) must
   use less than half of the available Flash memory. 
 - For Pico 2 with partitions: Your application must begin at the start of a partition,
   and the partition must be large enough to contain the old and new versions of your application.

Provided that all of these requirements are met, an OTA update can be started by
running:
```
python remote_picotool --secret hunter2 ota newfirmwarefile.uf2
```
The new firmware file must be in the `.bin` or `.uf2` format.

The firmware is uploaded and stored temporarily in Flash, at an address outside of the
existing program. This is necessary because the Pico's RAM is too small to store most
firmware files. If there is not enough space, then remote\_picotool will detect the problem
and report an error.

After uploading, the integrity of the temporary copy is checked using SHA256. If the upload
failed, an error is reported and the existing application continues to run. If the upload was ok, then
a special procedure in RAM will be executed to replace the current firmware with the
new firmware, and then the Pico is rebooted.

If the update fails for any reason, or the new firmware does not work,
the Pico can still be recovered by reprogramming with USB (hold down the BOOTSEL button
when plugging into USB).

## Known Issue: Partitions on Pico 2

The Pico 2 partition support allows for A/B firmware updates in which new firmware
can be installed alongside existing firmware, with the possibility to recover from
a problem by booting the older firmware. However, pico-wifi-settings doesn't support
this functionality yet, and will only use a single partition (whichever partition is
currently in use).

# Remote procedure calls into your firmware

remote\_picotool can be used to call functions within your firmware, if they are registered
as handlers by calling `wifi_settings_remote_set_handler()`. These calls are authenticated
using `update_secret` and data can be sent and received. This could be useful as a
general remote procedure call (RPC) system, allowing you to
activate some application functionality remotely without needing to implement a network API.
Here is an example of a handler function which dumps the value of a
variable named `control_status`:
```
#include "wifi_settings.h"
#define ID_GET_STATUS_HANDLER (ID_FIRST_USER_HANDLER + 0)

static int32_t remote_handler_get_status(
        uint8_t msg_type,
        uint8_t* data_buffer,
        uint32_t input_data_size,
        int32_t input_parameter,
        uint32_t* output_data_size,
        void* arg) {

    if (*output_data_size > sizeof(control_status)) {
        *output_data_size = sizeof(control_status);
    }
    memcpy(data_buffer, &control_status, (size_t) *output_data_size);
    return 0;
}
int main() {
    ...
    wifi_settings_remote_set_handler(ID_GET_STATUS_HANDLER, remote_handler_get_status, NULL);
    ...
}
```
A handler registered with `wifi_settings_remote_set_handler` can be called from Python
by importing remote\_picotool as a Python module. To do this, create a symlink to `remote_picotool` with a `.py`
extension, and then import the module from your Python program. Here is an example of
a Python function which will connect to a Pico W board and run `remote_handler_get_status`:
```
import remote_picotool

ID_GET_STATUS_HANDLER = remote_picotool.ID_FIRST_USER_HANDLER + 0

async def remote_handler_get_status() -> bytes:
    try:
        config = remote_picotool.RemotePicotoolCfg()
        reader, writer = await remote_picotool.get_pico_connection(config)
        client = remote_picotool.Client(config.update_secret_hash, reader, writer)
        (result_data, result_value) = await client.run(ID_GET_STATUS_HANDLER)
        return result_data
    finally:
        writer.close()
        await writer.wait_closed()
```
The board ID and update\_secret needed for access to Pico W will be taken from
`remote_picotool.cfg` or from environment variables (`PICO_ID` and `PICO_UPDATE_SECRET`).
To use command line parameters instead, call
`remote_picotool.RemotePicotoolCfg.add_config_options()` to add the parameters to
an `argparse.ArgumentParser` object and then pass the result of `parse_args` as
a parameter when calling the `RemotePicotoolCfg` constructor.

An example of the use of remote\_picotool as a Python module can be found in
[the ventilation-system example project](https://github.com/jwhitham/ventilation-system):
see `remote_status.py`.

# Other remote\_picotool features

With `-DWIFI_SETTINGS_REMOTE=2`,
remote\_picotool can also reboot a Pico into bootloader
mode (`remote_picotool reboot_bootloader`).
There is a feature to dump memory (`save`), which can be used with Flash or RAM, and there
is a feature to reprogram blocks of Flash outside of the current program (`load`).


# Technical notes

The remote service listens on TCP/IP port 1404.

Broadcasts to UDP port 1404 are used for searching for Pico devices.
Broadcast is used because multicast does not work reliably with typical home WiFi hotspots.

## Security

The protocol is encrypted with AES-256
and authenticated using HMAC-SHA256, so it does not rely on network security
and in principle you can update your Pico via the Internet if you wish, bearing in mind
that the protocol doesn't provide perfect forward secrecy (i.e. it's possible for an attacker
to recover all data from a network packet recording if your `update_secret` is discovered).

The encrypted connection is established after the client and server exchange 120-bit
random numbers ("challenges") which are given to HMAC-SHA256 along with the update secret
in order to generate four 256-bit values:

 - A response from the client to the server, proving that the client knows the secret.
 - A response from the server to the client, proving that the server knows the secret.
 - An AES-256 encryption key for messages from the client to the server.
 - An AES-256 encryption key for messages from the server to the client.

All four of these values will be different for every connection. After the responses
are exchanged successfully, all communications are encrypted. The details of the algorithm
can be seen in the C code ([wifi\_settings\_remote.c](../src/wifi_settings_remote.c))
and in Python code ([remote\_picotool](../remote_picotool)).

The AES-256 and SHA-256 implementations are reused from mbedtls, which is part of the
Pico SDK. On Pico 2, hardware support is used for SHA-256.

## Multicore support

On a Pico, access to Flash is shared by both CPU cores, and this can cause issues
when writing to Flash [described in detail here](https://github.com/raspberrypi/pico-sdk/blob/ee68c78d0afae2b69c03ae1a72bf5cc267a2d94c/src/rp2_common/pico_flash/include/pico/flash.h#L17-L49).
The setup app uses the `flash_safe_execute_core_init()` function to allow
writing to Flash when using both cores - see [setup.c](/setup/setup.c).

A simple way to avoid some problems is to use `update_reboot` instead of `update`, as
this stops the second CPU core before updating the wifi-settings file and reboots
immediately afterwards.

Other Flash-writing commands (`ota`, `load`, `update`) require the use of multicore lockout if
multiple CPUs are in use. You need to follow the directions in the Pico SDK to enable
safe multicore Flashing if you wish to use these commands in a multicore system.

## Board IDs

Board IDs consist of 16 hex digits and are unique to every Pico. The board ID
can be used by `remote_picotool` to find a particular Pico and distinguish
it from any others that may also be on your WiFi network. The board ID
should be used with the `--id` option.

The board ID is printed by the [example](../example) and [setup app](SETUP_APP.md) on the
USB serial port. You can also see the board ID by connecting a Pico by USB and
running `picotool info -d`. The ID appears as "flash id"
or "chipid" within "Device Information", e.g.
```
    Device Information
     type:              RP2040
     flash size:        2048K
     flash id:          0xE6614854D3B51718
```
or
```
    Device Information
     type:                   RP2350
     package:                QFN60
     chipid:                 0x7d47cf75b7a48bd7
```
The `0x` prefix is not used by pico-wifi-settings when referring to these board IDs,
which would be represented as `E6614854D3B51718` and `7D47CF75B7A48BD7`.
