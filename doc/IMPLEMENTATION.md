# Implementation details

## Connection state machine

[wifi\_settings\_connect.c](../src/wifi_settings_connect.c)
uses a state machine that runs periodically
(`PERIODIC_TIME_MS`, 1000ms). The periodic task
checks the connection state and takes action as appropriate.
Here are the states:

### DISCONNECTED

After successful initialisation, pico-wifi-settings is in the DISCONNECTED state. At any
time, pico-wifi-settings can be forced back into the DISCONNECTED state by calling
`wifi_settings_disconnect()`. In this state, the WiFi hardware is active but not
in use.

### TRY\_TO\_CONNECT 

Calling `wifi_settings_connect()` causes it to enter the TRY\_TO\_CONNECT state.

In this state, pico-wifi-settings waits for a minimum time delay
before beginning a WiFi scan. This time delay is configured by
`INITIAL_SETUP_TIME_MS` (for the first scan) and
`REPEAT_SCAN_TIME_MS` (for all subsequent scans). It prevents continuous scanning
attempts by enforcing a minimum time delay between scans. Once the time delay expires,
`cyw43_wifi_scan` is called and pico-wifi-settings enters the SCANNING state.

### SCANNING

In this state, pico-wifi-settings waits for the scan to complete
(`cyw43_wifi_scan_active()` returns false).
Each hotspot found by the scan is compared to those listed in the
[WiFi settings file](SETTINGS_FILE.md).

When the scan completes, the next state is either CONNECTING (if at least
one hotspot was found) or TRY\_TO\_CONNECT (if nothing was found - in which case,
the scan is restarted after a delay). The rules for choosing a hotspot are:

- The hotspot was found by the scan, and
- Since the most recent scan was started, there has not been any attempt to connect to this hotspot.

If more than one hotspot matches these rules, then the one with the smallest
number is chosen (i.e. `ssid1` is preferred to `ssid2`).

The transition to the CONNECTING state also involves a call to `cyw43_wifi_join`
with the SSID and password from the pico-wifi-settings file. If a BSSID is provided,
this is used instead of the SSID.

### CONNECTING

In this state, pico-wifi-settings waits for a successful connection, a timeout
or a connection error.

A successful connection is one where the Pico has been assigned an IPv4 address
via the selected hotspot. If this is achieved, pico-wifi-settings enters
the CONNECTED\_IP state.

A connection error is any error condition reported by `cyw43_wifi_link_status`.
If this occurs, then pico-wifi-settings returns to the SCANNING state. This does
not begin a new scan: instead, it repeats the actions which follow the end of
a scan (i.e. determine a hotspot to connect to).

A timeout is identified if `CONNECT_TIMEOUT_TIME_MS` milliseconds have elapsed
since `cyw43_wifi_join` was called. This is similar to a connection error. The
current connection attempt is aborted and pico-wifi-settings returns to the SCANNING
state.

### CONNECTED\_IP

In this state, pico-wifi-settings checks that the connection is still ok. If the link
has dropped, or no IPv4 address is known, it will return to the TRY\_TO\_CONNECT
state and rescan for hotspots.

### Error states

If the [WiFi settings file](SETTINGS_FILE.md) is empty (neither
`ssid1` or `bssid1` are defined), the state will be STORAGE\_EMPTY\_ERROR.
If initialisation failed, the state will be INITIALISATION\_ERROR.
If initialisation has been skipped, the state will be UNINITIALISED.

These states last until pico-wifi-settings is reinitialised, except for STORAGE\_EMPTY\_ERROR,
which can also be resolved by updating the file.
