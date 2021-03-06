import asyncio
import logging

import aioisotp

logging.basicConfig(level=logging.DEBUG)


class EchoServer(asyncio.Protocol):

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        # Echo back the same data
        self.transport.write(data)


async def main():
    network = aioisotp.ISOTPNetwork('vcan0',
                                    interface='virtual',
                                    receive_own_messages=True)
    with network.open():
        # Server uses protocol
        transport, protocol = await network.create_connection(EchoServer,
                                                              0x1CDADCF9,
                                                              0x1CDAF9DC)

        # Client uses streams
        reader, writer = await network.open_connection(0x1CDAF9DC, 0x1CDADCF9)

        writer.write(b'Hello world!')
        await writer.drain()
        response = await reader.read(4096)
        assert response == b'Hello world!'


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
