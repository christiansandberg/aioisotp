import asyncio
import binascii


class WrappedTransport(asyncio.WriteTransport):

    def __init__(self, transport):
        self._transport = transport

    def get_extra_info(self, name, default=None):
        return self._transport.get_extra_info(name, default)

    def write(self, payload):
        self._transport.write(b'<' + binascii.hexlify(payload) + b'>')

    def can_write_eof(self):
        return False

    def is_closing(self):
        return self._transport.is_closing()

    def close(self):
        self._transport.close()


class WrappedProtocol(asyncio.Protocol):

    def __init__(self, protocol, con_made_fut, loop):
        self._protocol = protocol
        self._con_made_fut = con_made_fut
        self._loop = loop
        self._buffer = bytearray()

    def connection_made(self, transport):
        wrapped = WrappedTransport(transport)
        self._con_made_fut.set_result(wrapped)
        self._protocol.connection_made(wrapped)

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
            self._loop.call_soon(self._protocol.data_received, payload)

    def connection_lost(self, exc):
        self._protocol.connection_lost(exc)

    def pause_writing(self):
        self._protocol.pause_writing()

    def resume_writing(self):
        self._protocol.resume_writing()


async def make_isotpserver_transport(protocol_factory, host, port, loop):
    protocol = protocol_factory()
    con_made = loop.create_future()
    await loop.create_connection(
        lambda: WrappedProtocol(protocol, con_made), host, port)
    transport = await con_made
    return transport, protocol
