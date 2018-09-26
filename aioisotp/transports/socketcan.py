import asyncio
import socket
import struct


async def make_socketcan_transport(protocol_factory, channel,
                                   rxid, txid, bs, st_min, max_wft, loop):
    SOL_CAN_ISOTP = socket.SOL_CAN_BASE + socket.CAN_ISOTP
    CAN_ISOTP_RECV_FC = 2

    sock = socket.socket(socket.AF_CAN, socket.SOCK_DGRAM, socket.CAN_ISOTP)
    sock.setblocking(False)

    opt = struct.pack('BBB', bs, st_min, max_wft)
    sock.setsockopt(SOL_CAN_ISOTP, CAN_ISOTP_RECV_FC, opt)

    if rxid > 0x7FF or txid > 0x7FF:
        rxid |= socket.CAN_EFF_FLAG
        txid |= socket.CAN_EFF_FLAG

    sock.bind((channel, rxid, txid))

    transport, protocol = await loop.create_connection(protocol_factory, sock=sock)
    return transport, protocol
