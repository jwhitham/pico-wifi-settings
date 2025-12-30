/**
 * Copyright (c) 2025 Jack Whitham
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * This pico-wifi-settings module manages the WiFi connection
 * by calling cyw43 and LwIP functions.
 *
 */



#define WIFI_SETTINGS_CONNECT_C
#include "wifi_settings/wifi_settings_configuration.h"
#include "wifi_settings/wifi_settings_connect.h"
#include "wifi_settings/wifi_settings_connect_internal.h"
#include "wifi_settings/wifi_settings_flash_storage.h"
#include "wifi_settings/wifi_settings_hostname.h"

#ifdef ENABLE_REMOTE_UPDATE
#include "wifi_settings/wifi_settings_remote.h"
#endif

#include "pico/binary_info.h"
#include "pico/error.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>


from .storage import get_value_for_key

struct wifi_state_t g_wifi_state;

class SSIDType(enum.Enum):
    NONE = 0
    BSSID = 1
    SSID = 2

class ConnectState(enum.Enum):
    UNINITIALISED = 0           # cyw43 hardware was not started
    INITIALISATION_ERROR = 1    # initialisation failed (see hw_error)
    STORAGE_EMPTY_ERROR = 2     # no WiFi details are known
    DISCONNECTED = 3            # call wifi_settings_connect() to connect
    TRY_TO_CONNECT = 4          # connection process begun
    SCANNING = 5                # scan running
    CONNECTING = 6              # connection running
    CONNECTED_IP = 7            # connection is ready for use
};

class SSIDScanInfo(enum.Enum):
    NOT_FOUND = 0               # this SSID was not found
    FOUND = 1                   # this SSID was found by the most recent scan
    ATTEMPT = 2                 # we attempted to connect to this SSID
    FAILED = 3                  # ... but it failed with an error
    TIMEOUT = 4                 # ... but it failed with a timeout
    BADAUTH = 5                 # ... but the password is wrong
    SUCCESS = 6                 # ... and it worked
    LOST = 7                    # we connected to this SSID but the connection dropped

IPV4_ADDRESS_SIZE = 16      # "xxx.xxx.xxx.xxx\0"
KEY_SIZE = 10               # e.g. "bssid0"

class WiFiState:
    cstate = ConnectState.UNINITIALISED
    ssid_scan_info = [SSIDScanInfo.NOT_FOUND * (MAX_NUM_SSIDS + 1)]
    selected_ssid_index = 0
    connect_timeout_time = 0
    scan_holdoff_time = 0
    hw_error = ""
    nic: typing.Any = None

g_wifi_state = WiFiState()

def has_no_wifi_details() -> bool:
    ssid_type, _, _ = __fetch_ssid(1)
    return ssid_type == SSIDType.NONE

def get_connect_status_text() -> typing.Optional[str]:
    if g_wifi_state.cstate == ConnectState.TRY_TO_CONNECT:
        return "WiFi did not find any known hotspot yet"

    if g_wifi_state.cstate == ConnectState.SCANNING:
        return "WiFi is scanning for hotspots"

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
    if g_wifi_state.nic is None:
        return ""

    link_status = g_wifi_state.nic.status()
    hw_status_text = {
        0: "CYW43_LINK_DOWN",
        1: "CYW43_LINK_JOIN",
        2: "CYW43_LINK_NOIP",
        3: "CYW43_LINK_UP",
        -1: "CYW43_LINK_FAIL",
        -2: "CYW43_LINK_NONET",
        -3: "CYW43_LINK_BADAUTH",
    }.get(link_status, str(link_status))
    rssi = g_wifi_state.nic.status('rssi')
    return "cyw43_wifi_link_status = {} scan_active = {} rssi = {}".format(
        hw_status_text,
        False, # network_cyw43_scan is synchronous
        rssi)

def get_ip_status_text() -> str:
    if ((g_wifi_state.nic is None)
    or not g_wifi_state.nic.ipconfig("has_dhcp4")):
        # Not connected
        return ""
    
    char addr_buf1[IPV4_ADDRESS_SIZE];
    char addr_buf2[IPV4_ADDRESS_SIZE];
    char addr_buf3[IPV4_ADDRESS_SIZE];
    (address, netmask) = g_wifi_state.nic.ipconfig("addr4")
    gateway = g_wifi_state.nic.ipconfig("gw4")
    return "IPv4 address = {} netmask = {} gateway = {}".format(
        address, netmask, gateway)

def get_ip() -> str:
    if ((g_wifi_state.nic is None) or not __wifi_is_connected()):
        # Not connected - return empty string
        return ""

    (address, _) = g_wifi_state.nic.ipconfig("addr4")
    return address

def get_ssid() -> str:
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
    if ((ssid_index >= 1) and (ssid_index <= MAX_NUM_SSIDS)):
        return g_wifi_state.ssid_scan_info[ssid_index].name

    return ""

def __wifi_is_connected() -> bool:
    return ((g_wifi_state.nic is not None)
        and g_wifi_state.nic.ipconfig("has_dhcp4"))

def __convert_string_to_bssid(text: str) -> bytes:
    # A BSSID is specified in the file as bssid1=01:23:45:67:89:ab
    # note 1 - ':' separators
    # note 2 - exactly 17 bytes
    if text_size != ((WIFI_BSSID_SIZE * 3) - 1):
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
    # Generate search key
    key = "bssid{}".format(ssid_index)

    ssid_size = WIFI_SSID_SIZE

    # A BSSID is specified in the file as bssid1=01:23:45:67:89:ab
    ssid = storage.get_value_for_key(key)
    bssid = __convert_string_to_bssid(ssid)
    if bssid:
        return (SSIDType.BSSID, ssid, bssid)

    # An SSID is specified in the file as ssid1=MyHotspotName
    # and must match exactly; SSIDs cannot contain characters recognised
    # as end of line or end of file (\r \n \xff \x00 \x1a)
    ssid = storage.get_value_for_key(key[1:])
    if ssid:
        return (SSIDType.SSID, ssid, b"")

    # Undefined SSID and BSSID
    return (SSIDType.NONE, "?", b"")

def __ensure_disconnected() -> None:
    if g_wifi_state.nic is not None:
        g_wifi_state.nic.disconnect()
    g_wifi_state.nic = None

def __begin_connecting() -> None:
    # This function is called after a scan, to begin connecting to a new hotspot.
    # It looks at the results of the scan and previous connections, via ssid_scan_info.
    __ensure_disconnected()

    # Which hotspot to connect to?
    g_wifi_state.selected_ssid_index = 0
    for ssid_index in range(1, MAX_NUM_SSIDS + 1):
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
    g_wifi_state.connect_timeout_time = __make_timeout_time_ms(CONNECT_TIMEOUT_TIME_MS)
    g_wifi_state.cstate = ConnectState.CONNECTING

    # Get the password
    key = "pass{}".format(g_wifi_state.selected_ssid_index)
    password = storage.get_value_for_key(key)

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
    # Mark the selected SSID as bad in some way (e.g. BADAUTH, TIMEOUT)
    # so that it won't be tried again. Go back to the SCANNING state.
    g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] = info
    g_wifi_state.cstate = ConnectState.SCANNING

def __has_valid_address() -> bool:
    char address_buf[IPV4_ADDRESS_SIZE];
    ip = get_ip()
    return ip and ip != "0.0.0.0"

def __begin_new_scan() -> None:
    # Begin a scan. We will reset everything we know about hotspots first.
    for ssid_index in range(1, MAX_NUM_SSIDS + 1):
        g_wifi_state.ssid_scan_info[ssid_index] = ConnectState.NOT_FOUND

    # Collect known SSIDs
    bssid_index: typing.Dict[bytes, int] = {}
    ssid_index: typing.Dict[str, int] = {}
    for ssid_index in range(1, MAX_NUM_SSIDS + 1):
        ssid_type, ssid, bssid = __fetch_ssid(ssid_index)
        if ssid_type == SSIDType.BSSID:
            bssid_index[bssid] = ssid_index
        elif ssid_type == SSIDType.SSID:
            ssid_index[ssid] = ssid_index
        else:
            break

    # Start the scan - it happens synchronously
    for found in g_wifi_state.nic.scan():
        ssid = found[0]
        bssid = found[1]
        if bssid in bssid_index:
            g_wifi_state.ssid_scan_info[bssid_index[bssid]] = ConnectState.NOT_FOUND

    // No more entries to try
    return 0;
    
    cyw43_wifi_scan_options_t opts;
    memset(&opts, 0, sizeof(opts));
    g_wifi_state.hw_error_code = cyw43_wifi_scan(g_wifi_state.cyw43, &opts, NULL, wifi_scan_callback);
    g_wifi_state.cstate = SCANNING;
    g_wifi_state.scan_holdoff_time = make_timeout_time_ms(REPEAT_SCAN_TIME_MS);
}

static void wifi_settings_periodic_callback(async_context_t* unused1, async_at_time_worker_t* unused2) {
    switch (g_wifi_state.cstate) {
        case TRY_TO_CONNECT:
            // In this state, we are not connected, and we are waiting for a holdoff time
            // before beginning a scan for available hotspots. If a scan is already running
            // (e.g. due to disconnecting during a scan) we wait for it to finish.
            ensure_disconnected();
            if (wifi_settings_has_no_wifi_details()) {
                // This is reached if the storage file contains no SSIDs.
                g_wifi_state.cstate = STORAGE_EMPTY_ERROR;
            } else if (time_reached(g_wifi_state.scan_holdoff_time) && !cyw43_wifi_scan_active(g_wifi_state.cyw43)) {
                begin_new_scan();
            }
            break;
        case SCANNING:
            // In this state, we are waiting for a hotspot scan to complete.
            // If it already completed, and we have some results, we can go directly to CONNECTING.
            if (!cyw43_wifi_scan_active(g_wifi_state.cyw43)) {
                begin_connecting();
            }
            break;
        case CONNECTING:
            // In this state, we are joining a WiFi hotspot, having found at least one
            // possibility during the scan.
            switch (cyw43_wifi_link_status(g_wifi_state.cyw43, CYW43_ITF_STA)) {
                case CYW43_LINK_DOWN:
                case CYW43_LINK_FAIL:
                case CYW43_LINK_NONET:
                    // Connection failed - this hotspot must have disappeared
                    give_up_connecting(FAILED);
                    break;
                case CYW43_LINK_BADAUTH:
                    // Connection failed because the password is incorrect
                    give_up_connecting(BADAUTH);
                    break;
                case CYW43_LINK_JOIN:
                case CYW43_LINK_NOIP:
                case CYW43_LINK_UP:
                    // Connection still in progress or completed
                    g_wifi_state.netif = netif_default;
                    if (wifi_is_connected() && has_valid_address()) {
                        // Successful
                        g_wifi_state.ssid_scan_info[g_wifi_state.selected_ssid_index] = SUCCESS;
                        g_wifi_state.cstate = CONNECTED_IP;
                    } else if (time_reached(g_wifi_state.connect_timeout_time)) {
                        // Connection failed with a timeout
                        give_up_connecting(TIMEOUT);
                    }
                    break;
                default:
                    // Fallback -> connection failure
                    give_up_connecting(FAILED);
                    break;
            }
            break;
        case CONNECTED_IP:
            // In this state we should be connected, but the connection could drop at any time
            if (!wifi_is_connected() || !has_valid_address()) {
                // Connection lost
                give_up_connecting(LOST);
                // It may be some time since the last scan, so scan again
                g_wifi_state.cstate = TRY_TO_CONNECT;
            }
            break;
        case STORAGE_EMPTY_ERROR:
            // This state is reached if the storage file contains no SSIDs.
            // Wait for the file to be updated.
            if (!wifi_settings_has_no_wifi_details()) {
                g_wifi_state.cstate = TRY_TO_CONNECT;
            }
            break;
        case INITIALISATION_ERROR:
        case UNINITIALISED:
        case DISCONNECTED:
            // nothing to do
            break;
        default:
            break;
    }
    // trigger again after the period
    g_wifi_state.periodic_worker.next_time =
        delayed_by_ms(g_wifi_state.periodic_worker.next_time,
                      PERIODIC_TIME_MS);
    async_context_add_at_time_worker(
        g_wifi_state.context,
        &g_wifi_state.periodic_worker);
}

int wifi_settings_init() {
    if (g_wifi_state.cstate != UNINITIALISED) {
        return PICO_ERROR_INVALID_STATE;
    }
    // Put wifi-settings library version into the binary info
    bi_decl_if_func_used(bi_program_feature("pico-wifi-settings v" WIFI_SETTINGS_VERSION_STRING));

    // Start with globals in known state
    memset(&g_wifi_state, 0, sizeof(g_wifi_state));
    g_wifi_state.cstate = UNINITIALISED;
    g_wifi_state.cyw43 = &cyw43_state; // from Pico SDK, lib/cyw43-driver (MAC layer)

    // Which country should be used?
    // You can put "country=<xy>" in the WiFi settings file to set a different value.
    // The code <xy> is a two-byte ISO-3166-1 country code
    // such as AU (Australia), SE (Sweden) or GB (United Kingdom).
    char value[2];
    uint value_size = sizeof(value);
    uint32_t country = PICO_CYW43_ARCH_DEFAULT_COUNTRY_CODE; // worldwide default

    if ((wifi_settings_get_value_for_key("country", value, &value_size))
    && (value_size == 2)) {
        country = CYW43_COUNTRY(value[0], value[1], 0);
    }

    // Set the hostname from wifi-settings "name=<xxx>" or use unique board id
    wifi_settings_set_hostname();

    // Hardware init
    g_wifi_state.hw_error_code = cyw43_arch_init_with_country(country);
    if (g_wifi_state.hw_error_code) {
        g_wifi_state.cstate = INITIALISATION_ERROR;
        return g_wifi_state.hw_error_code;
    }

    // After initialisation, any call to LWIP requires this lock (callback functions
    // are always holding it already, but this function is not a callback)
    cyw43_arch_lwip_begin();

    // Set up to connect to an access point
    cyw43_arch_enable_sta_mode();

    // State initialised
    g_wifi_state.connect_timeout_time = make_timeout_time_ms(CONNECT_TIMEOUT_TIME_MS);
    g_wifi_state.scan_holdoff_time = make_timeout_time_ms(INITIAL_SETUP_TIME_MS);
    g_wifi_state.cstate = DISCONNECTED;

    // Use cyw43 async context
    g_wifi_state.context = cyw43_arch_async_context();

    // Start periodic worker
    g_wifi_state.periodic_worker.next_time = g_wifi_state.scan_holdoff_time;
    g_wifi_state.periodic_worker.do_work = wifi_settings_periodic_callback;
    async_context_add_at_time_worker(
        g_wifi_state.context,
        &g_wifi_state.periodic_worker);

#ifdef ENABLE_REMOTE_UPDATE
    // Start remote access service
    g_wifi_state.hw_error_code = wifi_settings_remote_init();
#endif
    // set lwip hostname (overriding the default set by cyw43_cb_tcpip_init)
    netif_set_hostname(netif_default, wifi_settings_get_hostname());

    // Ready to run LWIP functions
    cyw43_arch_lwip_end();

    return g_wifi_state.hw_error_code;
}

void wifi_settings_deinit() {
    if (g_wifi_state.cstate == UNINITIALISED) {
        return;
    }
    ensure_disconnected();
    if (g_wifi_state.context) {
        // stop periodic task
        async_context_remove_at_time_worker(
            g_wifi_state.context,
            &g_wifi_state.periodic_worker);
    }
    g_wifi_state.context = NULL;
    cyw43_arch_deinit();
    g_wifi_state.cstate = UNINITIALISED;
    g_wifi_state.selected_ssid_index = 0;
}

void wifi_settings_connect() {
    if (g_wifi_state.cstate == DISCONNECTED) {
        // Try to connect when periodic worker is next called
        cyw43_arch_lwip_begin();
        if (g_wifi_state.cstate == DISCONNECTED) {
            g_wifi_state.cstate = TRY_TO_CONNECT;
        }
        cyw43_arch_lwip_end();
    }
}

void wifi_settings_disconnect() {
    // Immediate disconnect
    if ((g_wifi_state.cstate != UNINITIALISED)
    && (g_wifi_state.cstate != INITIALISATION_ERROR)) {
        cyw43_arch_lwip_begin();
        ensure_disconnected();
        g_wifi_state.cstate = DISCONNECTED;
        g_wifi_state.selected_ssid_index = 0;
        cyw43_arch_lwip_end();
    }
}

bool wifi_settings_is_connected() {
    bool rc = false;
    if (g_wifi_state.cstate == CONNECTED_IP) {
        // wifi_is_connected calls LWIP functions, so the lock is needed
        cyw43_arch_lwip_begin();
        rc = wifi_is_connected();
        cyw43_arch_lwip_end();
    }
    return rc;
}
