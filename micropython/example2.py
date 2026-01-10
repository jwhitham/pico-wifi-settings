# asyncio TCP server example
# 
# Currently (v1.28) there is no support for UDP endpoints in Micropython asyncio.
# Nor are there Protocols or Transports or Loop.create_server, so a TCP server
# is started with asyncio.start_server.
#

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


async def amain() -> None:

    print("Init")
    wifi_settings.init()
    print("Connect")
    wifi_settings.connect()
    port = 2000
    ip = wifi_settings.get_ip()
    while not ip:
        print("Await IP address")
        await asyncio.sleep(1)
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
