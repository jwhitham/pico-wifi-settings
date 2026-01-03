
import socket
import time
import wifi_settings

def __set_micropython_lwip_callback(sock, callback):
    """Internal: register a function which will be called whenever
    tcp_recv or tcp_accept is called for the provided socket.

    mypy should ignore this function as setsockopt does not match the usual
    CPython library definition.

    The magic number 20 is from Micropython extmod/modlwip.c."""
    return sock.setsockopt(0, 20, callback)

def recv_callback(s: socket.socket) -> None:
    try:
        b = s.recv(2000)
        while len(b) != 0:
            print("recv_callback", b)
            s.send(b)
            b = s.recv(2000)
        print("recv_callback connection closed")
    except OSError:
        # e.g. EAGAIN
        print("recv_callback more data available")

def listen_callback(s: socket.socket) -> None:
    (s2, v) = s.accept()
    print("listen_callback", v)
    __set_micropython_lwip_callback(s2, recv_callback)
    s2.setblocking(False)

def main() -> None:

    #ip = wifi_settings.get_ip()
    #while not ip:
        #print("Await IP address")
        #time.sleep(1)
        #ip = wifi_settings.get_ip()

    port = 2000
    print("Server", port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', port))
    __set_micropython_lwip_callback(s, listen_callback)
    s.listen(1)
    print("Init")
    wifi_settings.init()
    print("Connect")
    wifi_settings.connect()
    print("OK")

if __name__ == "__main__":
    main()
