# Setup app

The pico-wifi-settings setup app has an interactive, text mode user
interface which you can access by USB. Once installed on your Pico,
it allows you to search for WiFi hotspots and create/edit
the WiFi settings file.

# Requirements

 - USB connection to your Pico W
 - Serial terminal program capable of connecting to Pico W apps
   (for example, [PuTTY](https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html)
   or minicom)
 
# Installation

 - [Download the latest release .zip file here](https://github.com/jwhitham/pico-wifi-settings/releases)
 - Connect your Pico W to your computer with USB, holding down the BOOTSEL button
 - Open the downloaded .zip file and find the correct file for your Pico device
   - Pico W: use `setup_app__pico_w__<version>.uf2`
   - Pico 2 W: use `setup_app__pico2_w__<version>.uf2`
 - Drag and drop the `.uf2` file for your Pico model from the zip file to your Pico device
 - Connect to Pico W using your serial terminal program
   - More instructions can be found in the [Getting Started Guide, chapter 5](https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf)
   - Briefly, using minicom on Linux, enter `minicom -D /dev/ttyACM0`
   - On Windows, your Pico will appear as a COM port which you can use
     with [PuTTY](https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html) in its
     serial mode; to find the correct COM port number, look in the Device Manager.
 - Once connected to the serial port, press Enter to wake the application.

# First-time setup

The setup app has a retro MS-DOS-style text interface. If you find this unfamiliar,
then there's a user guide below (see Usage).

The easiest way to add a new hotspot to the WiFi settings file is to use
`Scan for a new hotspot`.

The connection status is shown near the top of the screen, for example:
```
    WiFi is connected to ssid2=MyHomeWiFi
    IPv4 address = 192.168.0.182 netmask = 255.255.255.0 gateway = 192.168.0.1
```
If you find that pico-wifi-settings cannot connect to your hotspot, you may have entered the
password incorrectly, in which case you can use `View and edit known hotspots`
to edit the password.

Once the connection is established, you might try `Perform connection test`
to see if you can ping other systems on your network or the Internet. Many
Internet sites respond to pings - for example, you can try the Google DNS server
with address 8.8.8.8.

The `Force disconnect/reconnect` option can be used to force pico-wifi-settings
to reread the WiFi settings file and reconnect to the highest-priority hotspot.

You may wish to set an update secret while using the setup app. This will allow
remote access to your Pico with [remote\_picotool](REMOTE.md), making it easy to
update the WiFi settings in the future.

# Usage

The setup app's text-based user interface may not be familiar, but it is not complex.
It is "menu-driven".

The app displays a series of choices (a "menu"), each associated with a number or letter.
When the app starts up, the menu appears like this:
```
    pico-wifi-settings setup app, version 0.1.0-abcdef01
    This Pico has board id 7D47CF75B7A48BD7

    WiFi is connected to ssid2=MyHomeWiFi
    IPv4 address = 192.168.0.182 netmask = 255.255.255.0 gateway = 192.168.0.1

    What would you like to do?
     1. Scan for a new hotspot
     2. View and edit known hotspots
     3. Perform connection test
     4. Force disconnect/reconnect
     5. Set update_secret for remote updates
     6. Edit other items in the wifi-settings file
     7. Reboot (return to bootloader)
    Press '1' .. '7' to select:
```
You press the key corresponding to the choice that you want. To scan for a new hotspot,
you would press `1`. Then you would see a list of available hotspots, like:
```
    pico-wifi-settings setup app, version 0.1.0-abcdef01
    This Pico has board id 7D47CF75B7A48BD7

    WiFi is disconnected
    cyw43_wifi_link_status = CYW43_LINK_DOWN scan_active = False rssi = 0

    Found 4 - please choose:

     1. MyHomeWifi                        | 64:69:33:1f:00:1f |   1 | -62 dB
     2. <unnamed>                         | ee:48:b8:57:9d:4e |   6 | -81 dB
     3. Random Other WiFi                 | e8:48:b8:57:9d:4e |   6 | -78 dB
     4. Next Door WiFi                    | 44:ad:c3:aa:10:31 |  11 | -79 dB
     5. Refresh
     6. Cancel
    Press '1' .. '6' to select:
```
As before, you press a button to choose one of them or cancel. 
Aside from menus, the app may also ask yes/no questions:
```
    WiFi passwords must be at least 8 characters.
    Try again? Press 'y' for yes, 'n' for no:
```
and it may require text entry, like this:
```
    Please enter the password for 'MyHomeWiFi':
    >
```
In this case you just type the requested text and press Enter. You can use backspace/delete
to delete characters, but the text editor is very simple and only allows adding/removing
characters at the end of the line. Only printable ASCII characters are supported - if you need
to use non-ASCII UTF-8 characters, you should [edit the
WiFi settings file on a PC](SETTINGS_FILE.md).

At any time, you can cancel the current action by pressing control-C. During text entry
you can also press control-Y to delete the whole line.

# Unsupported hotspot types

Some hotspot types are not supported (or have never been tested). These include:

 - hotspots using legacy authentication types (WEP, TKIP);
 - hotspots that have a "captive portal" page, as free public WiFi services often do,
   since it is not possible for the Pico to log in to the captive portal page;
 - hotspots that aren't supported by the `cyw43` driver.

WiFi hotspots do not need to offer Internet access, but they must have a DHCP server,
because the library does not provide a way to set a static IP address yet.

# Building from source with CMake

The source code for the setup application can be found [here](../setup) and can
be compiled like any other Pico project. A typical build process for Pico 2 W
looks like this:
```
    cd setup
    rm -rf build
    mkdir build
    cd build
    cmake -DWIFI_SETTINGS_REMOTE=2 -DPICO_BOARD=pico2_w ..
    make
```

# Building from source with Bazel

See the [Bazel instructions](/doc/BAZEL.md) for more details. A typical build step
for Pico 2 W looks like this:
```
    bazel build --platforms=@pico-sdk//bazel/platform:rp2350 \
        --@pico-sdk//bazel/config:PICO_BOARD=pico2_w  \
        --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//setup:setup_lwipopts \
        --@pico-sdk//bazel/config:PICO_STDIO_USB=1 \
        --//bazel/config:WIFI_SETTINGS_REMOTE=2 \
        --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
        --output_groups=+pico_uf2_files \
        //setup:setup
```
