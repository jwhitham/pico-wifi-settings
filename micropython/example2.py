
import socket
import time
import wifi_settings

MAGIC = 20

def recv_callback(s: socket.socket) -> None:
    b = s.recv(1)
    print("recv_callback", b)
    if len(b) != 0:
        s.send(b)

def listen_callback(s: socket.socket) -> None:
    (s2, v) = s.accept()
    print("listen_callback", v)
    s2.setsockopt(0, MAGIC, recv_callback)

def main() -> None:
    print("Init")
    wifi_settings.init()
    print("Connect")
    wifi_settings.connect()

    ip = wifi_settings.get_ip()
    while not ip:
        print("Await IP address")
        time.sleep(1)
        ip = wifi_settings.get_ip()

    port = 2000
    print("Server", ip, port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((ip, port))
    s.setsockopt(0, MAGIC, listen_callback)
    s.listen(1)
    print("OK")

if __name__ == "__main__":
    main()
