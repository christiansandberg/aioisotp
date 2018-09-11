ISO-TP for asyncio Python
=========================

This package implements ISO-TP_ over CAN as an asyncio_ transport layer,
enabling simultaneous receiving and transmitting messages with any number
of connections.

Raw CAN communication uses python-can_ which offers compatibility for many
different CAN interfaces and operating systems.
If SocketCAN is used on Python 3.7+, the transport is delegated to the kernel
if possible for better timing performance.


Why asynchronous?
-----------------

Asynchronous programming simplifies some possible use-cases:

* Full duplex receiving and transmitting on a single connection.
* Communicate on multiple connections simultaneously.
* Functional addressing where one request is sent out and all nodes respond,
  then processing the responses as they arrive.
* Implementing or simulating multiple servers.

No threads need to be handled with all the locking mechanisms required by it.


Installation
------------

Install from PyPI::

    $ pip install aioisotp


Documentation
-------------

A basic documentation can be built using Sphinx::

    $ python setup.py build_sphinx


Quick start
-----------

.. code:: python

    import asyncio
    import aioisotp


    class EchoServer(asyncio.Protocol):

        def connection_made(self, transport):
            self._transport = transport

        def data_received(self, data):
            # Echo back the same data
            self._transport.write(data)


    async def main():
        network = aioisotp.ISOTPNetwork(
            channel='vcan0', bustype='virtual', receive_own_messages=True)
        with network.open():
            # A server that uses a protocol
            transport, protocol = await network.create_connection(
                EchoServer, 0x1CDADCF9, 0x1CDAF9DC)

            # A client that uses streams
            reader, writer = await network.open_connection(
                0x1CDAF9DC, 0x1CDADCF9)

            writer.write(b'Hello world!')
            response = await reader.read(4095)
            assert response == b'Hello world!'


    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())


UDS
---

This package is meant to enable the use of other protocols that require
ISO-TP. One of the most common is UDS. A third party library like udsoncan_
or pyvit_ can be used to encode and decode payloads.

.. code:: python

    import aioisotp
    import udsoncan

    ...

    reader, writer = await network.open_connection(0x1CDAF9DC, 0x1CDADCF9)

    # Construct and send request
    request = udsoncan.Request(
        udsoncan.services.ReadDataByIdentifier, data=b'\xF1\x90')
    writer.write(request.get_payload())

    # Wait for response and decode the payload
    payload = await reader.read(4095)
    response = udsoncan.Response.from_payload(payload)

    print(response)
    print(response.data)


.. _ISO-TP: https://en.wikipedia.org/wiki/ISO_15765-2
.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _python-can: https://github.com/hardbyte/python-can/
.. _udsoncan: https://github.com/pylessard/python-udsoncan/
.. _pyvit: https://github.com/linklayer/pyvit/
