# pico-wifi-settings

This [Raspberry Pi Pico
W](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html#pico-2-family)
library manages WiFi connections for your Pico application. It provides:
 - [Flash storage for WiFi passwords and hotspot names](doc/SETTINGS_FILE.md) ("SSIDs"),
 - a background `async_context` service to automatically connect to them,
 - an optional [remote update service](doc/REMOTE.md), secured with AES-256, which allows
   you to update WiFi settings remotely,
 - an optional over-the-air (OTA) update service for uploading new firmware.

You can store details for up to 16 hotspots, and update them
at any time by USB or WiFi. This avoids any need to recompile Pico firmware
with new `WIFI_SSID` and `WIFI_PASSWORD` settings, which is required for
[Pico WiFi examples](https://github.com/raspberrypi/pico-examples/). You can
easily change your WiFi password or move your Pico to a different WiFi hotspot.

## Requirements

 - Raspberry Pi Pico W or Pico 2 W hardware
 - A "bare metal" C/C++ application for Pico (not FreeRTOS)
 - between 2kb and 13kb of code space depending on options used

pico-wifi-settings uses the `cyw43` driver and `lwip` network stack
which are provided with the
[Pico SDK](https://github.com/raspberrypi/pico-sdk/). This is
an open-source library with the same license as the Pico SDK.
The size can be reduced by
disabling optional [remote update features](doc/REMOTE.md).

## Storage

pico-wifi-settings stores WiFi hotspot names and passwords
in a Flash sector that isn't normally used by programs. This
["WiFi settings file" can be updated by USB or WiFi](doc/SETTINGS_FILE.md)
and can also be edited by installing the [setup app](doc/SETUP_APP.md).

The [WiFi settings file](doc/SETTINGS_FILE.md) is a simple text file like this:
```
ssid1=MyHomeWiFi
pass1=mypassword1234
ssid2=MyPhoneHotspot
pass2=secretpassword
country=GB
```
pico-wifi-settings will automatically scan for hotspots and connect to
hotspots matching the SSID names and passwords in the file.

# Setup app

You can try pico-wifi-settings without writing any code! The
[setup app](doc/SETUP_APP.md) has an interactive, text mode user
interface which you can access by USB. Once installed on your Pico.
It allows you to search for WiFi hotspots and create/edit
the WiFi settings file.

# Example app

A small example showing the usage of pico-wifi-settings can be found in
[example](example). It is [about 150 lines of C code](example/example.c).

This example connects to WiFi with pico-wifi-settings and then broadcasts
messages on UDP port 1234. You can receive these with tools such as
tcpdump, Wireshark or netcat:
```
    netcat -l -u -p 1234
```
Before this example can be used, you need to configure the WiFi settings file
in Flash. Use the setup app for that, or look at the
[WiFi settings file documentation](doc/SETTINGS_FILE.md).

# Remote updates

When pico-wifi-settings is built with default options, it is possible to [remotely
update](doc/REMOTE.md) the WiFi settings file. This feature is
already enabled in the [setup app](doc/SETUP_APP.md),
and in the [example application](example), and any other application
that includes the wifi\_settings library with default options.

There is some [documentation about the remote update features](doc/REMOTE.md).
The feature can be disabled permanently by using the build option `-DWIFI_SETTINGS_REMOTE=0`
or temporarily by not setting an `update_secret`.

The `update_secret` appears in the [WiFi settings file](doc/SETTINGS_FILE.md) and
sets a passphrase (a shared secret key) which is needed to send updates. Access is
secured using AES-256 encryption and each connection has a uniquely-negotiated key.

# Integration into your own Pico application

You can integrate pico-wifi-settings into your own Pico application with just a few lines of code!

There is an [integration guide which explains what you need to do
to add pico-wifi-settings to your application](doc/INTEGRATION.md).

You can also look at [a simple example of pico-wifi-settings](example) with about 150
lines of C code, or the more complex [setup application](doc/SETUP_APP.md)
[source code](setup).

# Where this came from

[I am a software engineer with embedded systems experience](https://www.jwhitham.org/).
I developed two personal projects using Pico W with WiFi and in both cases I found
a need to store a list of hotspots and passwords. I made a command-line interface
for WiFi setup which could be accessed via USB, and reused it in both projects. But
the implementations diverged and became harder to maintain, and it wasn't easy to
update WiFi settings (or anything else). So I decided to turn it into a reusable library
with all of the features I wanted. This is it!

You can read about [implementation details in this document](doc/IMPLEMENTATION.md).
