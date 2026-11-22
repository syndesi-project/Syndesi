Defaults
========

What Syndesi chooses when you don't. Any value you give explicitly takes precedence.

Adapters
--------

==================  ===========  =========================  ==========================
Adapter             Timeout      Stop conditions            Opens
==================  ===========  =========================  ==========================
``IP``              2 s          ``Continuation(0.2)``      at the first operation
``SerialPort``      2 s          ``Continuation(0.1)``      at the first operation
``Visa``            2 s          ``Continuation(0.1)``      at the first operation
``IPServer``        none         clients: ``Continuation``  at the first ``read()``
                                 ``(0.2)``
==================  ===========  =========================  ==========================

Serial line settings: 8 data bits, no parity, 1 stop bit, no flow control.

Protocols
---------

A protocol replaces the adapter's stop conditions, and sets the port or baudrate the
user left out.

.. list-table::
   :header-rows: 1
   :widths: 18 40 12 14

   * - Protocol
     - Stop conditions set on the adapter
     - Port
     - Protocol timeout
   * - ``Delimited``
     - ``Termination`` (``\n``)
     -
     - 2 s
   * - ``SCPI``
     - ``Termination`` (``\n``)
     - 5025
     - 5 s
   * - ``Raw``
     - unchanged
     -
     - 2 s
   * - ``Modbus`` (TCP)
     - assembled from the MBAP header
     - 502
     - 1 s
   * - ``Modbus`` (RTU)
     - ``Continuation``: 3.5 characters, 1.75 ms above 19200 baud
     -
     - 1 s
   * - ``Modbus`` (ASCII)
     - ``Termination`` (``\r\n``)
     -
     - 1 s

The protocol gives its timeout to the adapter, unless you chose the adapter's yourself.
A timeout you gave the adapter at its creation is used by the protocol too, when the
protocol isn't given one. See :ref:`timeouts`.

Modbus
------

=========================  ===================================
Addresses                  start at 1, as in device manuals
``byte_order``             ``"big"``
``word_order``             ``"big"``
String padding             ``"\0"``
String encoding            UTF-8
Server identity            ``server_id = b"syndesi"``
=========================  ===================================

Trace
-----

Adapters publish their traffic for ``syndesi-trace`` on the local multicast group
``239.255.42.99``, port ``12000``, restricted to this machine (TTL 1, loopback
interface).
