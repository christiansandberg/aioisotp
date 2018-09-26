"""
Start server::

    $ isotpserver -l 12345 -s 456 -d 123 vcan0
"""

import asyncio
import binascii
import logging

import aioisotp

logging.basicConfig(level=logging.DEBUG)

async def main():
    network = aioisotp.ISOTPNetwork('192.168.1.68:12345',
                                    interface='isotpserver')
    # Client uses streams
    reader, writer = await network.open_connection(0x456, 0x123)

    writer.write(b'\xff' * 32)
    await writer.drain()

    while True:
        payload = await reader.read(4095)
        print(binascii.hexlify(payload))


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
