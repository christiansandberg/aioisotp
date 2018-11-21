import asyncio
import logging
import struct

from ..constants import *
from ..exceptions import ISOTPError


LOGGER = logging.getLogger(__name__)


class ISOTPTransport(asyncio.Transport):

    logger = LOGGER

    def __init__(self, protocol, send_cb, block_size=0, st_min=0,
                 max_wft=0, loop=None, extra=None):
        super().__init__(extra)
        if send_cb is None:
            # Let send_raw be a no-op
            send_cb = lambda data: None
        self.send_raw = send_cb
        self.block_size = block_size
        self.st_min = st_min
        self.max_wft = max_wft
        self._protocol = protocol
        self._recv_buffer = bytearray()
        self._recv_block_count = 0
        self._recv_seq_no = 0
        self._recv_size = None
        self._send_queue = []
        self._send_seq_no = 0
        self._send_block_count = 0
        self._send_block_size = None
        self._send_st_min = None
        self._send_wf_count = 0
        self._closing = False
        if loop is not None:
            loop = asyncio.get_event_loop()
        self._loop = loop
        self._protocol.connection_made(self)

    def set_protocol(self, protocol):
        self._protocol = protocol

    def get_protocol(self):
        return self._protocol

    def close(self):
        self._closing = True
        if not self._send_queue:
            # Everything has been sent and we should close down
            self._protocol.connection_lost(None)

    def is_closing(self):
        return self._closing

    def can_write_eof(self):
        return False

    def get_write_buffer_size(self):
        return sum(len(buf) for buf in self._send_queue)

    def feed_data(self, data):
        """Feed raw CAN data to transport.

        :param bytearray data: CAN data
        """
        pci_type = data[0] >> 4
        if pci_type == FLOW_CONTROL_FRAME:
            self._handle_fc(data)
        elif self._closing:
            pass
        elif pci_type == SINGLE_FRAME:
            self._handle_sf(data)
        elif pci_type == FIRST_FRAME:
            self._handle_ff(data)
        elif pci_type == CONSECUTIVE_FRAME:
            self._handle_cf(data)

    def _reset_recv(self):
        self._recv_buffer.clear()
        self._recv_seq_no = 1
        self._recv_block_count = 0

    def _handle_sf(self, data):
        """Handle single frame."""
        self._reset_recv()
        self._recv_size = data[0] & 0xF
        self._recv_buffer.extend(data[1:])
        self._end_recv()

    def _handle_ff(self, data):
        """Handle first frame."""
        self._reset_recv()

        size = ((data[0] & 0xF) << 8) + data[1]
        if not size:
            # Size is > 4095
            size = struct.unpack_from('>L', data, 2)
            frame_payload = data[6:]
        else:
            frame_payload = data[2:]

        self._recv_size = size
        self._recv_buffer.extend(frame_payload)

        self._send_fc()

    def _handle_cf(self, data):
        """Handle consecutive frame."""
        seq_no = data[0] & 0xF
        if seq_no != self._recv_seq_no & 0xF:
            raise ISOTPError('Wrong sequence number')

        self._recv_buffer.extend(data[1:])

        self._recv_seq_no += 1
        self._recv_block_count += 1

        if len(self._recv_buffer) >= self._recv_size:
            # Last message received!
            self._end_recv()

        elif self._recv_block_count == self.block_size:
            self._send_fc()
            self._recv_block_count = 0

    def _send_fc(self, fs=CONTINUE_TO_SEND):
        """Send flow control frame."""
        self.logger.debug('Sending flow control frame')

        data = bytearray(3)
        data[0] = (FLOW_CONTROL_FRAME << 4) + fs
        data[1] = self.block_size
        data[2] = self.st_min
        self.send_raw(data)

    def _end_recv(self):
        data = bytes(self._recv_buffer[:self._recv_size])
        self._protocol.data_received(data)

    def write(self, payload):
        self._send_queue.append(bytearray(payload))
        if len(self._send_queue) == 1:
            # Nothing else is sending
            # Ask protocol to wait with next payload if possible
            self._protocol.pause_writing()
            self._start_send()

    def _start_send(self):
        """Start sending frames."""
        buffer = self._send_queue[0]
        self.logger.debug('Starting transfer of %d bytes', len(buffer))
        if len(buffer) < 8:
            self._send_sf()
        else:
            self._send_ff()

    def _send_sf(self):
        """Send single frame."""
        buffer = self._send_queue[0]
        size = len(buffer)

        data = bytearray()
        data.append((SINGLE_FRAME << 4) + size)
        data.extend(buffer)
        self.send_raw(data)

        self._end_send()

    def _send_ff(self):
        """Send first frame."""
        buffer = self._send_queue[0]
        size = len(buffer)

        data = bytearray(8)
        if size < 4096:
            data[0] = (FIRST_FRAME << 4) + (size >> 8)
            data[1] = size & 0xFF
            data[2:8] = buffer[0:6]
            del buffer[0:6]
        else:
            data[0] = FIRST_FRAME << 4
            data[1] = 0
            struct.pack_into('>L', data, 2, size)
            data[6:8] = buffer[0:2]
            del buffer[0:2]

        self.logger.debug('Sending first frame')
        self.send_raw(data)

        self.logger.debug('Waiting for flow control frame...')
        self._send_seq_no = 1
        self._send_block_count = 0

    def _handle_fc(self, data):
        """Handle flow control frame."""
        byte1, block_size, st_min = struct.unpack_from('BBB', data)
        fs = byte1 & 0xF
        if fs == CONTINUE_TO_SEND:
            self.logger.debug('block_size = %d, st_min = %d', block_size, st_min)
            self._send_block_size = block_size
            self._send_st_min = st_min
            # Ready to send next message
            self._send_cfs()
        elif fs == WAIT:
            # Do nothing
            self._send_wf_count += 1        
            if self._send_wf_count > self.max_wft:
                self.logger.error('Wait frame overrun')
        elif fs == OVERFLOW:
            self.logger.error('Buffer overflow/abort')
        else:
            self.logger.error('Invalid flow status')

    def _send_cfs(self):
        send_more = self._send_cf()
        if send_more:
            wait = self._get_wait_time()
            # Call ourselves after the wait
            self._loop.call_later(wait, self._send_cfs)

    def _send_cf(self):
        """Send consecutive frame."""
        buffer = self._send_queue[0]
        data = bytearray()
        data.append((CONSECUTIVE_FRAME << 4) + (self._send_seq_no & 0xF))
        data.extend(buffer[0:7])

        self.send_raw(data)

        del buffer[0:7]
        self._send_seq_no += 1
        self._send_block_count += 1

        if not buffer:
            # Last message sent, clean up
            self._end_send()
            return False
        elif self._send_block_count == self._send_block_size:
            self._send_block_count = 0
            self._send_wf_count = 0
            self.logger.debug('Waiting for flow control frame...')
            return False
        else:
            # Send another message
            return True

    def _get_wait_time(self):
        """Calculate the time in seconds between each consecutive message."""
        if self._send_st_min == 0:
            wait = 0
        elif self._send_st_min < 0x80:
            wait = self._send_st_min * 1e-3
        elif 0xF1 <= self._send_st_min <= 0xF9:
            wait = (self._send_st_min - 0xF0) * 1e-6
        else:
            wait = 0.127

        # Normally the event loop does not bother waiting for tasks
        # scheduled closer in time than the internal clock resolution.
        # In order to honor the requested minimum separation time, we make
        # sure the wait is long enough to not be skipped.
        # On Windows this is usually ~16 ms!
        if wait and hasattr(self._loop, '_clock_resolution'):
            wait = max(wait, self._loop._clock_resolution + 0.001)

        return wait

    def _end_send(self):
        """Clean up current transmission and possibly start next."""
        self.logger.debug('Transfer complete!')
        # Remove the transmission from the queue
        if self._send_queue:
            del self._send_queue[0]
        # Check if there are more transmissions queued up
        if self._send_queue:
            # Yes, start another send
            self._loop.call_soon(self._start_send)
        else:
            # Tell protocol that it can send more payloads
            self._protocol.resume_writing()
            if self._closing:
                # Everything has been sent and we should close down
                self._protocol.connection_lost(None)
