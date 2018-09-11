import asyncio
import binascii
import logging

import can

from .transport import ISOTPTransport
from .socketcan import make_socketcan_transport
from .constants import SINGLE_FRAME


LOGGER = logging.getLogger(__name__)


class ISOTPNetwork(can.Listener):
    """A CAN bus with one or more ISO-TP connections.

    Rest of keyword arguments will be passed to the python-can bus creator.
    
    :param can.BusABC bus:
        Existing python-can bus instance to use for sending.
    :param int block_size:
        Block size for receiving frames. Set to 0 for unlimited block size.
        May be tuned depending on CAN interface capabilities.
    :param int st_min:
        Minimum separation time between received frames.
    :param int max_wft:
        Maximum number of wait frames until signalling an error.
    :param asyncio.AbstractEventLoop loop:
        Event loop to use. Defaults to :func:`asyncio.get_event_loop`.
    """

    def __init__(self, bus=None, block_size=16, st_min=0, max_wft=0,
                 loop=None, **config):
        self.bus = bus
        self.block_size = block_size
        self.st_min = st_min
        self.max_wft = max_wft
        self.config = config
        self._rxids = {}
        if loop is None:
            loop = asyncio.get_event_loop()
        self._loop = loop

    def open(self):
        """Open connection to CAN bus and start receiving messages."""
        self.bus = can.Bus(**self.config)
        self.notifier = can.Notifier(self.bus, [self], 0.1, loop=self._loop)
        return self

    def close(self):
        """Disconnect from CAN bus."""
        self.notifier.stop()
        self.bus.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    async def create_connection(self, protocol_factory, rxid, txid):
        """Create a streaming transport connection with given transmit and
        receive IDs.

        This method will try to establish the connection in the background.
        When successful, it returns a `(transport, protocol)` pair.
        The transport will be a :class:`asyncio.WriteTransport` instance.

        Similar interface to the built-in
        :meth:`~asyncio.AbstractEventLoop.create_connection`.

        :param protocol_factory:
            Must be a callable returning a :class:`asyncio.Protocol` instance.
        :param int rxid:
            CAN ID to receive messages from.
        :param int txid:
            CAN ID to send messages to.
        """
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
                                   self.block_size, self.st_min, self.max_wft,
                                   loop=self._loop)
        self._rxids[rxid] = transport
        return transport, protocol

    async def open_connection(self, rxid, txid):
        """A wrapper for :meth:`create_connection` returning a
        (reader, writer) pair.

        The reader returned is a :class:`~asyncio.StreamReader` instance;
        the writer is a :class:`~asyncio.StreamWriter` instance.

        Similar interface to the built-in :func:`~asyncio.open_connection`.

        :param int rxid:
            CAN ID to receive messages from.
        :param int txid:
            CAN ID to send messages to.
        """
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await self.create_connection(lambda: protocol, rxid, txid)
        writer = asyncio.StreamWriter(transport, protocol, reader, self._loop)
        return reader, writer

    def send(self, txid, payload):
        """Send a single frame.

        Can be used for functional addressing.

        :param int txid:
            Transmit CAN ID.
        :param bytes payload:
            Payload that must be 7 bytes or less.
        """
        size = len(payload)
        assert size < 8, 'Only single frames can be sent without a transport'
        data = bytearray()
        data.append((SINGLE_FRAME << 4) + size)
        data.extend(payload)
        self.send_raw(txid, data)

    def send_raw(self, txid, data):
        LOGGER.debug('Sending raw frame: ID 0x%X - %s',
                     txid, binascii.hexlify(data).decode())
        msg = can.Message(arbitration_id=txid,
                          extended_id=txid > 0x7FF,
                          data=data)
        self.bus.send(msg)

    def on_message_received(self, msg):
        if msg.is_error_frame or msg.is_remote_frame:
            return

        transport = self._rxids.get(msg.arbitration_id)
        if transport is not None:
            transport.feed_data(msg.data)

    def on_error(self, exc):
        for transport in self._rxids.values():
            transport.get_protocol().connection_lost(exc)
