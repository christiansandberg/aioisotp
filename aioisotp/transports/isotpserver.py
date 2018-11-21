import asyncio
import binascii


class WrappedProtocol(asyncio.Protocol):

    def __init__(self, protocol, loop):
        self._protocol = protocol
        self._loop = loop
        self._buffer = bytearray()

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._protocol, attr)

    def data_received(self, data):
        self._buffer.extend(data)
        while True:
            start = self._buffer.find(b'<')
            end = self._buffer.find(b'>')
            if start == -1 or end == -1:
                # No complete message in buffer
                break
            payload = binascii.unhexlify(self._buffer[start+1:end])
            del self._buffer[:end+1]
            self._protocol.data_received(payload)


async def make_isotpserver_transport(protocol_factory, host, port, loop):
    protocol = protocol_factory()
    transport, _ = await loop.create_connection(
        lambda: WrappedProtocol(protocol, loop), host, port)

    # Monkey patch the write method in transport
    raw_write = transport.write
    transport.write = lambda payload: raw_write(
        b'<' + binascii.hexlify(payload) + b'>')

    return transport, protocol
