import logging

import aioisotp


logging.basicConfig(level=logging.DEBUG)


network = aioisotp.SyncISOTPNetwork(channel='vcan0', interface='virtual', receive_own_messages=True)
server = network.create_sync_connection(0x456, 0x123)
with network.open():
    client = network.create_sync_connection(0x123, 0x456)
    client.send(b'123456789')
    payload = server.recv(1)
    assert payload == b'123456789'
