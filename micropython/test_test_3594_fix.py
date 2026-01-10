import wifi_settings, time
wifi_settings.init()
wifi_settings.connect()

ip1 = ""
while ip1 == "":
    ip1 = wifi_settings.get_ip()
    time.sleep(1)
    print("Await ip address")

print("IP address is", ip1)
import test_3594_fix
test_3594_fix.test(ip1)
