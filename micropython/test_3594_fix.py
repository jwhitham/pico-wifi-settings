"""To use this test program:

On a Micropython board with LWIP network support

(1) initialise networking so the board has an IP address "<IP>"
(2) import test_3594_fix
(3) test_3594_fix.test("<IP>")

On another computer on the same network send a UDP packet e.g. with netcat on Linux:

    echo 'hello there' | nc -u <IP> 1234

and you should see, from Micropython:

    Message received from (<address>, <port>)

and the other computer receives the following message:

    Thank you, here is an echo!
    hello there

If the UDP callback doesn't work, then there will be no response.
"""

import socket

def __set_micropython_lwip_callback(sock, callback):
    """Register a user callback function used within modlwip.c.

    The magic number 20 is from Micropython, file extmod/modlwip.c,
    function lwip_socket_setsockopt, "if (opt == 20) { ... }".
    """
    return sock.setsockopt(0, 20, callback)

def __responder_recv(udp_sock: socket.socket) -> None:
    """Called when a UDP message is received."""
    (packet, addr) = udp_sock.recvfrom(1000)

    print("Message received from", addr)

    packet = b"Thank you, here is an echo!\r\n" + packet

    udp_sock.sendto(packet, addr)

def test(ip_address: str, port = 1234):
    """Test issue 3594 is fixed."""
    g_responder_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    g_responder_socket.bind((ip_address, port))
    __set_micropython_lwip_callback(g_responder_socket, __responder_recv)
    print("Ready to receive UDP messages on", ip_address, port)

