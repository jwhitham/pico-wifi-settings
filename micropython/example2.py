
import socket
try:
    # Running on MicroPython?
    import wifi_settings
    skip_wifi_settings = False
except ImportError:
    # Not running on MicroPython - use plain sockets library
    skip_wifi_settings = True
try:
    import typing
except ImportError:
    pass
import asyncio

class ProtocolForTCP(asyncio.Protocol):
    transport: typing.Optional[asyncio.Transport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if isinstance(transport, asyncio.Transport):
            self.transport = transport

    def data_received(self, data: bytes) -> None:
        if self.transport:
            self.transport.write(data)

class ProtocolForUDP(asyncio.DatagramProtocol):
    transport: typing.Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport) -> None:
        # note https://github.com/python/cpython/issues/90352 prevents proper type checking in Python <= 3.11
        self.transport = transport

    def datagram_received(self, data: bytes, addr: typing.Any) -> None:
        if self.transport:
            self.transport.sendto(data, addr)


async def amain() -> None:

    if skip_wifi_settings:
        ip = "127.0.0.1"
    else:
        print("Init")
        wifi_settings.init()
        print("Connect")
        wifi_settings.connect()
        ip = wifi_settings.get_ip()
        while not ip:
            print("Await IP address")
            await asyncio.sleep(1)
            ip = wifi_settings.get_ip()

    loop = asyncio.get_running_loop()
    tcp_service = await loop.create_server(ProtocolForTCP, host=ip, port=1234)
    await loop.create_datagram_endpoint(ProtocolForUDP, local_addr=(ip, 1234))
    print("Servers:", ip)
    await tcp_service.serve_forever()

def main() -> None:
    asyncio.run(amain())

if __name__ == "__main__":
    main()
