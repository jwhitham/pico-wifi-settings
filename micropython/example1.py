
print("Example")
import time
import wifi_settings

print("Init")
wifi_settings.init()
print("Connect")
wifi_settings.connect()

def test_handler(msg_type, data_buffer, input_data_size, input_parameter, arg):

    if -input_parameter != input_data_size:
        return (0, 1)

    assert arg == 1234
    print("Test size", input_data_size)
    value = -10
    for i in range(input_data_size):
        if data_buffer[i] == 0x41:
            value -= 1
        data_buffer[i] ^= 0xac

    return (input_data_size, value)

ID_USER = wifi_settings.ID_FIRST_USER_HANDLER
wifi_settings.set_handler(ID_USER, test_handler, 1234)

try:
    ip1 = "X"
    while True:
        ip2 = wifi_settings.get_ip()
        if ip1 != ip2:
            ip1 = ip2
            print("State change")
            print("get_ip =", ip1)
            print("has_no_wifi_details =", wifi_settings.has_no_wifi_details())
            print("get_connect_status_text =", wifi_settings.get_connect_status_text())
            print("get_hw_status_text =", wifi_settings.get_hw_status_text())
            print("get_ip_status_text =", wifi_settings.get_ip_status_text())
            print("get_ssid =", wifi_settings.get_ssid())
            print("get_ssid_status =", wifi_settings.get_ssid_status(1))
            print("is_connected =", wifi_settings.is_connected())
            print("")

        time.sleep(0.9)
except KeyboardInterrupt:
    wifi_settings.disconnect()
    wifi_settings.deinit()
