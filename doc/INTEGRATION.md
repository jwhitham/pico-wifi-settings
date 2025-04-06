# Integrating pico-wifi-settings into your own Pico application

You can integrate pico-wifi-settings into your own Pico application
with just a few lines of code:
```
    #include "wifi_settings.h"                  // << add this
    int main() {
        stdio_init_all();
        if (wifi_settings_init() != 0) {        // << and add this
            panic(...);
        }
        wifi_settings_connect();                // << and add this
        // and that's it...
    }
```
The following steps go through the process in more detail for
a [CMake](https://cmake.org) project stored in Git,
similar to all of the official Pico projects. If you are using
[Bazel](https://bazel.build) then there are some [Bazel-specific instructions](/doc/BAZEL.md).

You can also look at [a simple example](/example) with about 150
lines of C code, or the more complex [setup app](/doc/SETUP_APP.md).

## Import pico-wifi-settings

Import pico-wifi-settings as a Git submodule. Go to
the root of your project and enter:
```
    git submodule add https://github.com/jwhitham/pico-wifi-settings wifi_settings
```
A directory named `wifi_settings` will be created
containing the latest version of the library.

## Modify CMakeLists.txt to import the library

`CMakeLists.txt` should be modified to add the `wifi_settings` subdirectory.
```
    add_subdirectory(wifi_settings build)
```
Then, the `target_link_libraries` rule for your project should be extended to
add `wifi_settings`.
```
    target_link_libraries(your_app
            pico_cyw43_arch_lwip_threadsafe_background
            wifi_settings
            pico_stdlib
        )
```

### Additional configuration for LwIP and mbedtls

If your project has not previously used WiFi you will also need
to add one of the WiFi driver targets to `target_link_libraries`, e.g.
`pico_cyw43_arch_lwip_background` or `pico_cyw43_arch_lwip_poll`.

You will also need `lwipopts.h` in the project directory (this configures
LwIP). You can copy an example from [here](../example).

If you are using [the remote update feature](REMOTE.md), you need `mbedtls_config.h` too.
You can copy an example from [here](../example). The remote update feature is
optional and can be disabled by using the build option `-DWIFI_SETTINGS_REMOTE=0`.

## Include the header file

Your main C/C++ source file (containing `main()`) should be modified to include
`wifi_settings.h`:
```
    #include "wifi_settings.h"
```

## Modify your main function

Your `main()` function should be modified to call `wifi_settings_init()` once on startup.

 - This must *replace* any call to `cyw43` initialisation functions, because
   these are called from `wifi_settings_init()` (with the correct country code).
 - The call should be after `stdio_init_all()`.
 - If the call returns a non-zero value, an error has occurred. You do not have
   to handle this error; it is still safe to call other `wifi_settings` functions,
   but they will not work and will return error codes where appropriate.

Your application should also call `wifi_settings_connect()` when it wishes to connect
to WiFi. This can be called immediately after `wifi_settings_init()` or at any later
time. `wifi_settings_connect()` does not block, as the connection takes
place in the background.

All other modifications are optional. You can now rebuild your application
and it will include the pico-wifi-settings features.

# Optional modifications

Your application can call `wifi_settings_is_connected()` at any time
to determine if the WiFi connection is available or not.

Your application can call various status functions at any time
to get a text report on the connection status. This can be useful for debugging.
Each function should be passed a `char[]` buffer for the output, along with the
size of the buffer.

 - `wifi_settings_get_connect_status_text()` produces a line of
   text showing the connection status, e.g.  `WiFi is connected to ssid1=MyHomeWiFi`.
 - `wifi_settings_get_hw_status_text()` produces a line of
   text describing the status of the `cyw43` hardware driver; this will be empty
   if the hardware is not initialised.
 - `wifi_settings_get_ip_status_text()` produces a line of
   text describing the status of the `lwip` network stack e.g. IP address; this will be empty
   if unconnected.

There is also a function to report the current connection state
(see [implementation details](IMPLEMENTATION.md)). `wifi_settings_get_ssid_status()` returns
a pointer to a static string, indicating the status of a connection attempt to
an SSID, e.g. `SUCCESS`, `NOT FOUND`.

Your application can call `wifi_settings_disconnect()` to force disconnect,
or `wifi_settings_deinit()` to deinitialise the driver, but this is never necessary
and these steps can be left out. They exist to allow the application to shut down WiFi,
e.g. to save power, or in order to control the WiFi hardware directly for some other
purpose. For example, the setup app uses this feature to perform its own WiFi scan.
