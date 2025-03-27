# Creating and updating a WiFi settings file

pico-wifi-settings stores WiFi hotspot names and passwords
in a Flash sector that isn't normally used by programs. This
is called the "WiFi settings file". It is similar to a file on a disk,
except that it is always at the same location, and the size is
limited to 4096 bytes.

The file can be updated in several ways:
 - using the [setup](SETUP_APP.md),
 - by USB, using [picotool](https://github.com/raspberrypi/picotool),
 - by WiFi, when the pico-wifi-settings remote update feature is enabled.

The USB and WiFi methods have the advantage that you can create the file on
another computer and store backup copies of it. It is just a text file, and it
can be edited using any text editor. Here is an example of typical contents:
```
    ssid1=MyHomeWiFi
    pass1=mypassword1234
    ssid2=MyPhoneHotspot
    pass2=secretpassword
    country=GB
```
pico-wifi-settings will automatically scan for hotspots and connect to
hotspots matching the SSID names and passwords in the file.

# Creating the file with the setup app

The simplest way to create the WiFi settings file is to install
the [setup app](SETUP_APP.md) on your Pico. This has an interactive
text-mode user interface that allows you to scan for WiFi hotspots
and store them in the file.

# Creating the file on a PC

To edit the file on a PC, use any text editor to create a text file
similar to the example above. Then,
use [picotool](https://github.com/raspberrypi/picotool) to send the file
via USB.

Each line in the file should contain a key and a value, separated by `=`.

The file must have at least `ssid1` or `bssid1`, otherwise there will
be no connection attempts, and pico-wifi-settings will stay in the
STORAGE\_EMPTY\_ERROR state.

You can also use the following:

 - `ssid<N>` - SSID name for hotspot N (a number from 1 to 16)
 - `pass<N>` - Password for hotspot N
 - `country` - Your two-letter country code from [ISO-3166-1](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes)
 - `update_secret` - The shared secret for [remote updates](REMOTE.md)
 - `bssid<N>` - The BSSID ID for hotspot N
 - `name` - The hostname of the Pico (sent to DHCP servers)

# Copying the WiFi settings file by USB

You can use [picotool](https://github.com/raspberrypi/picotool) to copy the
file from your PC to your Pico via USB.

picotool is part of the Pico SDK. 
You need to build picotool with USB support for your OS (or download a pre-built copy).

To use picotool,
boot the Pico in bootloader mode by holding down the BOOTSEL button while plugging it
into USB. In bootloader mode, you can upload files with picotool. The address has to
be specified:

 - On Pico W, use `0x101ff000` as the address.
 - On Pico 2 W, use `0x103fe000` as the address.

You must also rename your WiFi settings file so that it ends with `.bin` as 
picotool is not able to upload files unless they are `.bin`, `.elf` or `.uf2`.

Here is a sample upload command for Pico W (RP2040):
```
    picotool load -o 0x101ff000 mywifisettings.bin
```
and the equivalent for Pico 2 W (RP2350):
```
    picotool load -o 0x103fe000 mywifisettings.bin
```
Note that on Pico 2 W, the final block in Flash can't be safely
used because of the workaround for bug RP2350-E10. The next-to-last block is used instead.

# Copying the WiFi settings file by WiFi

You can also send an updated WiFi settings file by WiFi using the
[remote update service](REMOTE.md) and remote\_picotool. But of course,
this requires the WiFi connection to be already working, so it is not useful
for first-time setup. See the [remote update service](REMOTE.md) documentation
for instructions.

# Backing up a WiFi settings file

picotool can be used to download WiFi settings files from a Pico W:
```
    picotool save -r 0x101ff000 0x10200000 backup.bin
```
and Pico 2 W (RP2350):
```
    picotool save -r 0x103fe000 0x103ff000 backup.bin
```
Characters after the end of the file will be copied (usually either 0x00 or 0xff).
These can be safely deleted using your text editor.

# File format details

The file format is very simple so that it can be read by a simple algorithm
that doesn't require much code space. The parser ignores any line that it
doesn't understand, and skips any keys that are not known. Here are the rules:

 - The key and the value should be separated only by an `=` character, e.g. `ssid1=HomeWiFi`.
 - Lines that don't match the form `key=value` are completely ignored;
   you can add text, comments etc. in order to help you manage your configuration.
 - On a line that does match `key=value`, whitespace is NOT ignored.
   Be careful to avoid adding extra spaces around `=`.
   A space before `=` will be part of the key, and a space after `=` will be part of the value.
 - Unix and Windows line endings are supported.
 - The maximum size of the file is 4096 bytes.
 - Values can contain any printable UTF-8 character.
 - Keys can also contain any printable UTF-8 character except for '='.
 - There is no maximum size for a key or a value (except for the file size).
 - Values can be zero length.
 - Keys must be at least 1 byte.
 - If a key appears more than once in the file, the first value is used.
 - The end of the file is the first byte with value 0x00, 0xff or 0x1a, or the 4097th byte,
   whichever comes first.

# WiFi settings

 - `ssid<N+1>` is only checked if `ssid<N>` is present.
 - The number reflects the priority. Lower numbers take priority over higher
   numbers when more than one SSID is found.
 - If `pass<N>` is not specified then pico-wifi-settings will assume
   an open WiFi hotspot.
 - If both `bssid<N>` and `ssid<N>` are specified, then the BSSID is used
   and the SSID is ignored.
 - If you don't specify a country, the default worldwide settings are used, which might work
   slightly less well (e.g. fewer WiFi channels are supported).
 - `bssid<N>` should be specified as
   a `:`-separated lower-case MAC address, e.g. `01:23:45:67:89:ab`. BSSIDs are
   not normally required and should only be used if you have a special requirement
   e.g. a "hidden" hotspot without am SSID name.
 - If the DHCP server on your LAN also acts as DNS, then the hostname specified with `name=`
   can be used with the `--address` option of remote\_picotool: this can
   be faster than searching for a board, and easier than using an IP address.
 - If `update_secret` is not present (or empty) [remote updates](REMOTE.md) are disabled.

# Custom keys and values

The WiFi settings file can have keys which are not used by the wifi\_settings library.
Your application can obtain their values using the `wifi_settings_get_value_for_key()` function.
This can be a useful way to store additional configuration data for your Pico application.
For example you might use it to store encryption keys, server addresses, user names
or any other setting that you may wish to update without rebuilding your application.

`wifi_settings_get_value_for_key` uses a linear search, starting at the beginning
of the file. This search does not backtrack and is fast because of the simplistic
nature of the file format. However, in algorithmic terms, this is not the best way
to implement or search a key/value store, and if you need frequent access to keys/values,
you may wish to implement something better (e.g. use a hash table to implement a dictionary)
or just load the values when your application starts up and then store them elsewhere.
