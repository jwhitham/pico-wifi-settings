
print("Example")
import time
import wifi_settings

print("Init")
wifi_settings.init()
print("Connect")
wifi_settings.connect()

ID_TEST_HANDLER_1 = wifi_settings.ID_FIRST_USER_HANDLER + 1
ID_TEST_HANDLER_2 = wifi_settings.ID_FIRST_USER_HANDLER + 2
ID_TEST_HANDLER_3 = wifi_settings.ID_FIRST_USER_HANDLER + 3
INT_MIN = -0x80000000
INT_MAX = 0x7fffffff

def test_handler_1(msg_type, data_buffer, input_data_size, input_parameter, arg):
    """This test handler echoes the input back, XOR'ing it with a constant 0xac.
    The input parameter is expected to be -input_data_size.
    The output value is -10 minus the number of 0x41 bytes in the input data."""

    print("test_handler_1:", input_data_size, input_parameter)
    assert msg_type == ID_TEST_HANDLER_1
    assert arg == 1234
    assert len(data_buffer) == wifi_settings.MAX_DATA_SIZE
    if -input_parameter != input_data_size:
        return (0, -1)

    value = -10
    for i in range(input_data_size):
        if data_buffer[i] == 0x41:
            value -= 1
        data_buffer[i] ^= 0xac

    return (input_data_size, value)

def test_handler_2(msg_type, data_buffer, input_data_size, input_parameter, arg):
    """This test handler generates output. The input parameter specifies the
    number of bytes to generate."""

    print("test_handler_2:", input_data_size, input_parameter)
    assert msg_type == ID_TEST_HANDLER_2
    assert arg == "A"
    assert len(data_buffer) == wifi_settings.MAX_DATA_SIZE

    if 0 < input_parameter <= wifi_settings.MAX_DATA_SIZE:
        for i in range(input_parameter):
            data_buffer[i] = (i + 1) & 0xff

    return (input_parameter, input_parameter ^ 1)

def test_handler_3(msg_type, data_buffer, input_data_size, input_parameter, arg):
    """This test handler produces no output bytes. It checks the bounds of the inputs and outputs."""

    print("test_handler_3:", input_data_size, input_parameter)
    assert msg_type == ID_TEST_HANDLER_3
    assert arg == test_handler_3
    if input_parameter == INT_MIN:
        return (0, -1)
    if input_parameter == INT_MAX:
        return (0, -2)
    if input_parameter == input_data_size:
        return (0, -3)
    if input_parameter == -1:
        return (0, INT_MIN)
    if input_parameter == -2:
        return (0, INT_MAX)
    if input_parameter == -3:
        return (0, INT_MAX + 1)
    if input_parameter == -4:
        return (0, INT_MIN - 1)
    if input_parameter == -5:
        return (0, 0x123456789abcde)

    return (0, -4)

wifi_settings.set_handler(ID_TEST_HANDLER_1, test_handler_1, 1234)
wifi_settings.set_handler(ID_TEST_HANDLER_2, test_handler_2, "A")
wifi_settings.set_handler(ID_TEST_HANDLER_3, test_handler_3, test_handler_3)

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
