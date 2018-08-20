import asyncio
import socket
import struct

try:
    SOL_CAN_BASE        = socket.SOL_CAN_BASE if hasattr(socket, 'SOL_CAN_BASE') else 100
    SOL_CAN_ISOTP       = SOL_CAN_BASE + socket.CAN_ISOTP
    CAN_ISOTP_RECV_FC   = 2
except AttributeError:
    pass


async def make_socketcan_transport(protocol_factory, channel,
                                   rxid, txid, bs, st_min, max_wft):
    sock = socket.socket(socket.AF_CAN, socket.SOCK_DGRAM, socket.CAN_ISOTP)
    sock.setblocking(False)

    opt = struct.pack('BBB', bs, st_min, max_wft)
    sock.setsockopt(SOL_CAN_ISOTP, CAN_ISOTP_RECV_FC, opt)

    sock.bind((channel, rxid, txid))

    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_connection(protocol_factory, sock=sock)
    return transport, protocol
