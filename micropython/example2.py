
import asyncio
import wifi_settings

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

    ip = wifi_settings.get_ip()
    while not ip:
        print("Await IP address")
        await asyncio.sleep(1)
        ip = wifi_settings.get_ip()

    port = 2000
    print("Server", ip, port)
    server = await asyncio.start_server(serve_callback, ip, port)
    await asyncio.sleep(1000)

def main() -> None:
    asyncio.run(amain())

if __name__ == "__main__":
    main()
