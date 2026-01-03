
import socket
import time
import wifi_settings

def __set_micropython_lwip_callback(sock, callback): # mypy should ignore this function
    sock.setsockopt(0, 20, callback)

def recv_callback(s: socket.socket) -> None:
    try:
        b = s.recv(2000)
        while len(b) != 0:
            print("recv_callback", b)
            s.send(b)
            b = s.recv(2000)
    except OSError:
        # e.g. EAGAIN
        pass

def listen_callback(s: socket.socket) -> None:
    (s2, v) = s.accept()
    print("listen_callback", v)
    __set_micropython_lwip_callback(s2, recv_callback)
    s2.setblocking(False)

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
    __set_micropython_lwip_callback(s, listen_callback)
    s.listen(1)
    print("OK")

if __name__ == "__main__":
    main()
