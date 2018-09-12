import asyncio
import threading
import queue

from .network import ISOTPNetwork


class SyncISOTPNetwork(ISOTPNetwork):
    """A variant of :class:`aioisotp.ISOTPNetwork` for use in a synchronous
    environment.

    An event loop will be run in a separate thread when :meth:`open` is called.

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
    """

    def __init__(self, bus=None, block_size=16, st_min=0, max_wft=0, **config):
        loop = asyncio.new_event_loop()
        self._thread = None
        super().__init__(bus, block_size, st_min, max_wft, loop, **config)

    def open(self):
        self._thread = threading.Thread(target=self._task)
        self._thread.start()
        return super().open()

    def _task(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def create_sync_connection(self, rxid, txid):
        """Create a connection for synchronous operation.

        :param int rxid:
            CAN ID to receive messages from.
        :param int txid:
            CAN ID to send messages to.

        :returns:
            An object with a :meth:`~aioisotp.sync.SyncConnection.recv` and a
            :meth:`~aioisotp.sync.SyncConnection.send` method.
        :rtype: aioisotp.sync.SyncConnection
        """
        coro = self.create_connection(SyncConnection, rxid, txid)
        if self._thread is None:
            _, protocol = self._loop.run_until_complete(coro)
        else:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            _, protocol = fut.result(timeout=1)
        return protocol
 
    def close(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(1)
        self._thread = None
        super().close()


class SyncConnection(asyncio.Protocol):
    """A class created using
    :meth:`~aioisotp.SyncISOTPNetwork.create_sync_connection`
    """

    def __init__(self):
        self.queue = queue.Queue()
        self._loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        self._transport = transport

    def data_received(self, payload):
        self.queue.put_nowait(payload)

    def connection_lost(self, exc):
        if exc is not None:
            self.queue.put_nowait(exc)

    def recv(self, timeout=None):
        """Receive next payload.

        :param float timeout:
            Max time to wait in seconds.
        
        :returns:
            Payload if available within timeout, else None.
        :rtype: bytes
        """
        try:
            payload = self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(payload, Exception):
            raise payload
        return payload

    def send(self, payload):
        """Send a payload.

        :param bytes payload:
            Payload to send.
        """
        self._loop.call_soon_threadsafe(self._transport.write, payload)

    def empty(self):
        while not self.queue.empty():
            self.queue.get()
