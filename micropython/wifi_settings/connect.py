#
#  Copyright (c) 2025 Jack Whitham
# 
#  SPDX-License-Identifier: BSD-3-Clause
# 
#  This pico-wifi-settings module manages the WiFi connection
#  by calling network.WLAN functions.
# 
#

from . import storage, configuration

import enum
import typing

# Micropython-specific imports:
import machine # type: ignore
import micropython # type: ignore
from time import ticks_add, ticks_ms, ticks_diff # type: ignore

class SSIDType(enum.Enum):
    NONE = 0
    BSSID = 1
    SSID = 2

class ConnectState(enum.Enum):
    UNINITIALISED = 0           # cyw43 hardware was not started
    INITIALISATION_ERROR = 1    # initialisation failed
    STORAGE_EMPTY_ERROR = 2     # no WiFi details are known
    DISCONNECTED = 3            # call wifi_settings_connect() to connect
    TRY_TO_CONNECT = 4          # connection process begun
    # SCANNING = 5              # scan running (N/A on Micropython as scans are synchronous)
    CONNECTING = 6              # connection running
    CONNECTED_IP = 7            # connection is ready for use

class SSIDScanInfo(enum.Enum):
    NOT_FOUND = 0               # this SSID was not found
    FOUND = 1                   # this SSID was found by the most recent scan
    ATTEMPT = 2                 # we attempted to connect to this SSID
    FAILED = 3                  # ... but it failed with an error
    TIMEOUT = 4                 # ... but it failed with a timeout
    BADAUTH = 5                 # ... but the password is wrong
    SUCCESS = 6                 # ... and it worked
    LOST = 7                    # we connected to this SSID but the connection dropped

class Cyw43LinkStatus(enum.Enum):
    CYW43_LINK_DOWN = 0
    CYW43_LINK_JOIN = 1
    CYW43_LINK_NOIP = 2
    CYW43_LINK_UP = 3
    CYW43_LINK_FAIL = -1
    CYW43_LINK_NONET = -2
    CYW43_LINK_BADAUTH = -3

WIFI_BSSID_SIZE = 6

class WiFiState:
    cstate = ConnectState.UNINITIALISED
    ssid_scan_info = [SSIDScanInfo.NOT_FOUND for _ in range(configuration.MAX_NUM_SSIDS + 1)]
    selected_ssid_index = 0
    connect_timeout_time = 0
    scan_holdoff_time = 0
    hw_error: str = ""
    nic: typing.Any = None
    timer: typing.Any = None

g_wifi_state = WiFiState()

def has_no_wifi_details() -> bool:
    """Determine if the WiFi settings file is empty.

    If the file is empty or not found, pico-wifi-settings will be unable to connect. See README.md
    for instructions on how to provide settings."""
    ssid_type, _, _ = __fetch_ssid(1)
    return ssid_type == SSIDType.NONE

def get_connect_status_text() -> typing.Optional[str]:
    """Get a report on the current connection status (as a string)."""
    if g_wifi_state.cstate == ConnectState.TRY_TO_CONNECT:
        return "WiFi did not find any known hotspot yet"

    if g_wifi_state.cstate == ConnectState.CONNECTING:
        ssid_type, ssid, _ = __fetch_ssid(g_wifi_state.selected_ssid_index)
        return "WiFi is connecting to {}ssid{}={}".format(
                "b" if (ssid_type == SSIDType.BSSID) else "",
                g_wifi_state.selected_ssid_index,
                ssid)

    if g_wifi_state.cstate == ConnectState.CONNECTED_IP:
        ssid_type, ssid, _ = __fetch_ssid(g_wifi_state.selected_ssid_index)
        return "WiFi is connected to {}ssid{}={}".format(
                "b" if (ssid_type == SSIDType.BSSID) else "",
                g_wifi_state.selected_ssid_index,
                ssid)

    if g_wifi_state.cstate == ConnectState.DISCONNECTED:
        return "WiFi is disconnected"

    if g_wifi_state.cstate == ConnectState.UNINITIALISED:
        return "WiFi uninitialised"

    if g_wifi_state.cstate == ConnectState.INITIALISATION_ERROR:
        return "WiFi init error: " + g_wifi_state.hw_error

    if g_wifi_state.cstate == ConnectState.STORAGE_EMPTY_ERROR:
        return "No WiFi details have been stored - unable to connect"

    return "WiFi status is unknown ({})".format(g_wifi_state.cstate)

def get_hw_status_text() -> str:
    """Get a report on the network hardware (cyw43) status (e.g. signal strength)."""
    if g_wifi_state.nic is None:
        return ""

    link_status = g_wifi_state.nic.status()
    try:
        hw_status_text = Cyw43LinkStatus(link_status).name
    except ValueError:
        hw_status_text = str(link_status)

    rssi = g_wifi_state.nic.status('rssi')
    return "cyw43_wifi_link_status = {} scan_active = {} rssi = {}".format(
        hw_status_text,
        False, # network_cyw43_scan is synchronous
        rssi)

def get_ip_status_text() -> str:
    """Get a report on the IP stack status (e.g. IP address)."""
    if ((g_wifi_state.nic is None)
    or not g_wifi_state.nic.ipconfig("has_dhcp4")):
        # Not connected
        return ""
    
    (address, netmask) = g_wifi_state.nic.ipconfig("addr4")
    gateway = g_wifi_state.nic.ipconfig("gw4")
    return "IPv4 address = {} netmask = {} gateway = {}".format(
        address, netmask, gateway)

def get_ip() -> str:
    """Get the IP address by itself (as a string).

    Returns "" if not known."""
    if ((g_wifi_state.nic is None) or not g_wifi_state.nic.ipconfig("has_dhcp4")):
        # Not connected - return empty string
        return ""

    (address, _) = g_wifi_state.nic.ipconfig("addr4")
    return address

def get_ssid() -> str:
    """Return the current SSID (as a string)."""
    if g_wifi_state.cstate in (
            ConnectState.CONNECTING,
            ConnectState.CONNECTED_IP):
        _, ssid, _ = __fetch_ssid(g_wifi_state.selected_ssid_index)
        # The ssid will be '?' if the SSID is unknown (e.g. if
        # the wifi-settings file was updated to remove the SSID while connected).
        return ssid

    # Not connected - return empty string
    return ""

def get_ssid_status(ssid_index: int) -> str:
    """Return the status of the specified SSID as a string.

    This is one of:
        NOT_FOUND   # this SSID was not found
        FOUND       # this SSID was found by the most recent scan
        ATTEMPT     # we attempted to connect to this SSID
        FAILED      # ... but it failed with an error
        TIMEOUT     # ... but it failed with a timeout
        BADAUTH     # ... but the password is wrong
        SUCCESS     # ... and it worked
        LOST        # we connected to this SSID but the connection dropped
    """

    if ((ssid_index >= 1) and (ssid_index <= configuration.MAX_NUM_SSIDS)):
        return g_wifi_state.ssid_scan_info[ssid_index].name

    return ""

def __convert_string_to_bssid(text: str) -> bytes:
    """Internal. Convert a BSSID (text) to six bytes.

    A BSSID is specified in the file as bssid1=01:23:45:67:89:ab
    - note 1 - ':' separators
    - note 2 - exactly 17 bytes
    This is converted to six bytes, or zero bytes on error.
    """
    if len(text) != ((WIFI_BSSID_SIZE * 3) - 1):
        # Malformed BSSID - not exactly 17 bytes
        return b""

    for i in range(WIFI_BSSID_SIZE - 1):
        if text[(i * 3) + 2] != ':':
            # Malformed BSSID - not ':' separator
            return b""

    bssid = b""
    for i in range(WIFI_BSSID_SIZE):
        copy = text[i * 3 : (i * 3) + 2]
        try:
            bssid += bytes((int(copy, 16), ))
        except ValueError:
            # Malformed BSSID - not a hex number
            return b""

    return bssid

def __fetch_ssid(ssid_index: int) -> typing.Tuple[SSIDType, str, bytes]:
    """Internal. Fetch SSID or BSSID name from the wifi settings file."""

    # Generate search key
    key = "bssid{}".format(ssid_index)

    # A BSSID is specified in the file as bssid1=01:23:45:67:89:ab
    ssid = storage.get_value_for_key(key) or ""
    bssid = __convert_string_to_bssid(ssid)
    if bssid:
        return (SSIDType.BSSID, ssid, bssid)

    # An SSID is specified in the file as ssid1=MyHotspotName
    # and must match exactly; SSIDs cannot contain characters recognised
    # as end of line or end of file (\r \n \xff \x00 \x1a)
    ssid = storage.get_value_for_key(key[1:]) or ""
    if ssid:
        return (SSIDType.SSID, ssid, b"")

    # Undefined SSID and BSSID
    return (SSIDType.NONE, "?", b"")

def __ensure_disconnected() -> None:
    """Internal. Force disconnection from the current hotspot (if any)."""
    if g_wifi_state.nic is not None:
        g_wifi_state.nic.disconnect()

def __make_timeout_time_ms(delta_ms: int) -> int:
    """Internal. Make a timeout time, ms in the future."""
    return ticks_add(ticks_ms(), delta_ms)

def __time_reached(time_abs: int) -> int:
    """Internal. Return true if time_abs is in the past."""
    return ticks_diff(ticks_ms(), time_abs) >= 0

def __begin_connecting() -> None:
    """Internal. This function is called after a scan, to begin connecting to a new hotspot.

    It looks at the results of the scan and previous connections, via ssid_scan_info.
    The first hotspot in the FOUND state will be attempted. If no hotspot is in the FOUND
    state, then the connection will return to the TRY_TO_CONNECT state (forcing a rescan)."""
    __ensure_disconnected()

    # Which hotspot to connect to?
    g_wifi_state.selected_ssid_index = 0
    for ssid_index in range(1, configuration.MAX_NUM_SSIDS + 1):
        if g_wifi_state.ssid_scan_info[ssid_index] == SSIDScanInfo.FOUND:
            g_wifi_state.selected_ssid_index = ssid_index
            break

    if g_wifi_state.selected_ssid_index == 0:
        # There are no available hotspots to connect to, either because the scan
        # didn't find anything, or everything is FAILED, TIMEOUT, BADAUTH or LOST.
        # In this case we should scan again.
        g_wifi_state.cstate = ConnectState.TRY_TO_CONNECT
        return

    # Begin connecting
    g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] = SSIDScanInfo.ATTEMPT
    g_wifi_state.connect_timeout_time = __make_timeout_time_ms(configuration.CONNECT_TIMEOUT_TIME_MS)
    g_wifi_state.cstate = ConnectState.CONNECTING

    # Get the password
    key = "pass{}".format(g_wifi_state.selected_ssid_index)
    password = storage.get_value_for_key(key) or ""

    # Get the BSSID or SSID
    ssid_type, ssid, bssid = __fetch_ssid(g_wifi_state.selected_ssid_index)
    if ssid_type == SSIDType.NONE:
        # No valid SSID or BSSID - this could happen if the storage was updated
        # between scanning and connecting. Force a rescan
        g_wifi_state.selected_ssid_index = 0
        g_wifi_state.cstate = ConnectState.TRY_TO_CONNECT
        return

    # Begin connection
    if ssid_type == SSIDType.BSSID:
        g_wifi_state.nic.connect(ssid="", bssid=bssid, key=password)
    else:
        g_wifi_state.nic.connect(ssid=ssid, key=password)

def __give_up_connecting(info: SSIDScanInfo) -> None:
    """Internal. Mark the selected SSID as bad in some way (e.g. BADAUTH, TIMEOUT)
    so that it won't be tried again. Go back to the CONNECTING state."""
    g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] = info
    g_wifi_state.cstate = ConnectState.CONNECTING
    __begin_connecting()

def __has_valid_address() -> bool:
    """Internal. Return true if the WLAN interface has an IPv4 address assigned by DHCP."""
    ip = get_ip()
    return (ip != "") and (ip != "0.0.0.0")

def __scan() -> None:
    """Internal. Scan for known hotspots (while disconnected).

    The scan is synchronous due to Micropython limitations."""

    # Begin a scan. We will reset everything we know about hotspots first.
    for i in range(1, configuration.MAX_NUM_SSIDS + 1):
        g_wifi_state.ssid_scan_info[i] = SSIDScanInfo.NOT_FOUND

    # Collect known SSIDs
    bssid_index: typing.Dict[bytes, int] = {}
    ssid_index: typing.Dict[str, int] = {}
    for i in range(1, configuration.MAX_NUM_SSIDS + 1):
        ssid_type, ssid, bssid = __fetch_ssid(i)
        if ssid_type == SSIDType.BSSID:
            bssid_index[bssid] = i 
        elif ssid_type == SSIDType.SSID:
            ssid_index[ssid] = i
        else:
            break

    # Start the scan - it happens synchronously on Micropython
    for found in g_wifi_state.nic.scan():
        ssid = found[0]
        bssid = found[1]
        if bssid in bssid_index:
            g_wifi_state.ssid_scan_info[bssid_index[bssid]] = SSIDScanInfo.FOUND
        elif ssid in ssid_index:
            g_wifi_state.ssid_scan_info[ssid_index[ssid]] = SSIDScanInfo.FOUND

    g_wifi_state.cstate = ConnectState.CONNECTING
    g_wifi_state.scan_holdoff_time = __make_timeout_time_ms(configuration.REPEAT_SCAN_TIME_MS)
    __begin_connecting()

def __periodic_callback(_) -> None:
    """Internal. Called periodically to check the connection or search for a hotspot.

    Period is PERIODIC_TIME_MS. This is called via the schedule() function so it is
    able to do anything that can normally be done in Python code."""

    if g_wifi_state.cstate == ConnectState.TRY_TO_CONNECT:
        # In this state, we are not connected, and we are waiting for a holdoff time
        # before beginning a scan for available hotspots. If a scan is already running
        # (e.g. due to disconnecting during a scan) we wait for it to finish.
        __ensure_disconnected()
        if has_no_wifi_details():
            # This is reached if the storage file contains no SSIDs.
            g_wifi_state.cstate = ConnectState.STORAGE_EMPTY_ERROR
        elif __time_reached(g_wifi_state.scan_holdoff_time):
            # No need to check cyw43_wifi_scan_active here as scans are synchronous
            __scan()

    elif g_wifi_state.cstate == ConnectState.CONNECTING:
        # In this state, we are joining a WiFi hotspot, having found at least one
        # possibility during the scan.
        link_status = g_wifi_state.nic.status()
        if link_status in (Cyw43LinkStatus.CYW43_LINK_DOWN,
                           Cyw43LinkStatus.CYW43_LINK_FAIL,
                           Cyw43LinkStatus.CYW43_LINK_NONET):
            # Connection failed - this hotspot must have disappeared
            __give_up_connecting(SSIDScanInfo.FAILED)
        elif link_status == Cyw43LinkStatus.CYW43_LINK_BADAUTH:
            # Connection failed because the password is incorrect
            __give_up_connecting(SSIDScanInfo.BADAUTH)
        elif link_status in (Cyw43LinkStatus.CYW43_LINK_JOIN,
                             Cyw43LinkStatus.CYW43_LINK_NOIP,
                             Cyw43LinkStatus.CYW43_LINK_UP):
            # Connection still in progress or completed
            if __has_valid_address():
                # Successful
                g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] = SSIDScanInfo.SUCCESS
                g_wifi_state.cstate = ConnectState.CONNECTED_IP
            elif __time_reached(g_wifi_state.connect_timeout_time):
                # Connection failed with a timeout
                __give_up_connecting(SSIDScanInfo.TIMEOUT)
            else:
                # Fallback -> connection failure
                __give_up_connecting(SSIDScanInfo.FAILED)

    elif g_wifi_state.cstate == ConnectState.CONNECTED_IP:
        # In this state we should be connected, but the connection could drop at any time
        if not __has_valid_address():
            # Connection lost
            __give_up_connecting(SSIDScanInfo.LOST)
            # It may be some time since the last scan, so scan again
            g_wifi_state.cstate = ConnectState.TRY_TO_CONNECT
    elif g_wifi_state.cstate == ConnectState.STORAGE_EMPTY_ERROR:
        # This state is reached if the storage file contains no SSIDs.
        # Wait for the file to be updated.
        if not has_no_wifi_details():
            g_wifi_state.cstate = ConnectState.TRY_TO_CONNECT
    else:
        # nothing to do / invalid state
        pass

def __periodic_callback_isr(_) -> None:
    """Internal. Called periodically to check the connection or search for a hotspot.

    This function can be called as a timer interrupt."""
    micropython.schedule(__periodic_callback, 0)

def init() -> None:
    """Initialise pico-wifi-settings for Micropython."""
    if g_wifi_state.cstate != ConnectState.UNINITIALISED:
        # init() not allowed in this state
        raise ValueError()

    g_wifi_state.cstate = ConnectState.INITIALISATION_ERROR
    try:
        # Set up to connect to an access point
        import network # type: ignore
        g_wifi_state.nic = network.WLAN(network.WLAN.IF_STA)
        g_wifi_state.nic.active(True)
    except Exception as e:
        # init() not available as there is no WLAN support
        g_wifi_state.hw_error = str(e)
        raise NotImplementedError() from None

    # Country code setting - not available for Micropython as CYW43 is already initialised
    # Hostname setting - not available for Micropython as netif_set_hostname can't be called

    # State initialised - we can scan immediately because CYW43 was already initialised by Micropython
    g_wifi_state.connect_timeout_time = __make_timeout_time_ms(configuration.CONNECT_TIMEOUT_TIME_MS)
    g_wifi_state.scan_holdoff_time = __make_timeout_time_ms(0)
    g_wifi_state.cstate = ConnectState.DISCONNECTED
    g_wifi_state.selected_ssid_index = 0

    # Start periodic worker
    g_wifi_state.timer = machine.Timer(-1, period=configuration.PERIODIC_TIME_MS,
                      callback=__periodic_callback_isr,
                      mode=machine.Timer.PERIODIC, hard=True)

    # #ifdef ENABLE_REMOTE_UPDATE
    # // Start remote access service
    # g_wifi_state.hw_error_code = wifi_settings_remote_init();
    # #endif

def deinit() -> None:
    """Deinitialise pico-wifi-settings for Micropython (disconnect and stop periodic task)."""
    if g_wifi_state.cstate == ConnectState.UNINITIALISED:
        return
    
    __ensure_disconnected()
    if g_wifi_state.timer is not None:
        g_wifi_state.timer.deinit()
    g_wifi_state.timer = None

    if g_wifi_state.nic is not None:
        g_wifi_state.nic.active(False)
    g_wifi_state.nic = False

    g_wifi_state.cstate = ConnectState.UNINITIALISED
    g_wifi_state.selected_ssid_index = 0

def connect() -> None:
    """Connect to WiFi if possible, using the settings in Flash.

    The actual connection may take some time to be established, and
    may not be possible. Call is_connected() to see if
    the connection is ready."""

    if g_wifi_state.cstate == ConnectState.DISCONNECTED:
        # Try to connect when periodic worker is next called
        g_wifi_state.cstate = ConnectState.TRY_TO_CONNECT

def disconnect() -> None:
    """Disconnect from WiFi immediately."""
    if ((g_wifi_state.cstate != ConnectState.UNINITIALISED)
    and (g_wifi_state.cstate != ConnectState.INITIALISATION_ERROR)):
        __ensure_disconnected()
        g_wifi_state.cstate = ConnectState.DISCONNECTED
        g_wifi_state.selected_ssid_index = 0

def is_connected() -> bool:
    """Determine if connection is ready."""
    if g_wifi_state.cstate == ConnectState.CONNECTED_IP:
        return __has_valid_address()
    return False
