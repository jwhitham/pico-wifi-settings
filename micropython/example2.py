
import socket
import time
import wifi_settings

import asyncio

async def serve_callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        b = await reader.readexactly(1)
        while b != b"\x04":
            writer.write(b)
            b = await reader.readexactly(1)
        await writer.drain()
        writer.close()
    except EOFError:
        pass


def __set_micropython_lwip_callback(sock, callback):
    """Internal: register a function which will be called whenever
    tcp_recv or tcp_accept is called for the provided socket.

    mypy should ignore this function as setsockopt does not match the usual
    CPython library definition.

    The magic number 20 is from Micropython extmod/modlwip.c."""
    return sock.setsockopt(0, 20, callback)

async def amain() -> None:

    print("Init")
    wifi_settings.init()
    print("Connect")
    wifi_settings.connect()
    port = 2000
    ip = wifi_settings.get_ip()
    while not ip:
        print("Await IP address")
        time.sleep(1)
        ip = wifi_settings.get_ip()
    print("Server", ip, port)
    foo = await asyncio.start_server(serve_callback, ip, port)
    print(foo)
    print(dir(foo))
    await asyncio.sleep(1000)

def main() -> None:
    asyncio.run(amain())

if __name__ == "__main__":
    main()
