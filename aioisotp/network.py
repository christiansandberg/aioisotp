import asyncio
import binascii
import logging

import can

from .transport import ISOTPTransport
from .socketcan import make_socketcan_transport
from .constants import SINGLE_FRAME


LOGGER = logging.getLogger(__name__)


class ISOTPNetwork(can.Listener):

    def __init__(self, bus=None, block_size=16, st_min=0, max_wft=0, **config):
        self.bus = bus
        self.block_size = block_size
        self.st_min = st_min
        self.max_wft = max_wft
        self.config = config
        self._rxids = {}

    def open(self):
        self.bus = can.Bus(**self.config)
        loop = asyncio.get_event_loop()
        self.notifier = can.Notifier(self.bus, [self], 0.1, loop=loop)
        return self

    def close(self):
        self.notifier.stop()
        self.bus.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    async def create_connection(self, protocol_factory, rxid, txid):
        if 'socketcan' in (self.config.get('bustype'), self.config.get('interface')):
            try:
                return await make_socketcan_transport(
                    protocol_factory, self.config.get('channel'), rxid, txid,
                    self.block_size, self.st_min, self.max_wft)
            except Exception as exc:
                LOGGER.warning('Could not use SocketCAN ISO-TP: %s', exc)

        return self._make_userspace_transport(protocol_factory, rxid, txid)

    def _make_userspace_transport(self, protocol_factory, rxid, txid):
        protocol = protocol_factory()
        send_cb = lambda data: self.send_raw(txid, data)
        transport = ISOTPTransport(protocol, send_cb,
                                   self.block_size, self.st_min, self.max_wft)
        self._rxids[rxid] = transport
        return transport, protocol

    async def open_connection(self, rxid, txid):
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await self.create_connection(lambda: protocol, rxid, txid)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        return reader, writer

    def send(self, txid, payload):
        size = len(payload)
        assert size < 8, 'Only single frames can be sent without a transport'
        data = bytearray()
        data.append((SINGLE_FRAME << 4) + size)
        data.extend(payload)
        self.send_raw(txid, data)

    def send_raw(self, txid, data):
        LOGGER.debug('Sending raw frame: %s', binascii.hexlify(data))
        fc = can.Message(arbitration_id=txid,
                         extended_id=txid > 0x7FF,
                         data=data)
        self.bus.send(fc)

    def on_message_received(self, msg):
        if msg.is_error_frame or msg.is_remote_frame:
            return

        transport = self._rxids.get(msg.arbitration_id)
        if transport is not None:
            transport.feed_can_data(msg.data)
