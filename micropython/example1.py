
print("Example")
import time
import wifi_settings

print("Init")
wifi_settings.init()
print("Connect")
wifi_settings.connect()
try:
    while True:
        print("has_no_wifi_details =", wifi_settings.has_no_wifi_details())
        print("get_connect_status_text =", wifi_settings.get_connect_status_text())
        print("get_hw_status_text =", wifi_settings.get_hw_status_text())
        print("get_ip_status_text =", wifi_settings.get_ip_status_text())
        print("get_ip =", wifi_settings.get_ip())
        print("get_ssid =", wifi_settings.get_ssid())
        print("get_ssid_status =", wifi_settings.get_ssid_status(1))
        print("is_connected =", wifi_settings.is_connected())
        time.sleep(0.9)
        print("\x1b[2J")
except KeyboardInterrupt:
    wifi_settings.disconnect()
    wifi_settings.deinit()
