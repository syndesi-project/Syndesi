Adapters, protocols, drivers
============================

Talking to a device mixes three different questions:

1. **How do the bytes travel?** A TCP socket, a serial cable, a USB link through VISA.
2. **What do the messages look like?** Lines of text, SCPI commands, Modbus frames.
3. **What does the device do?** Measure a voltage, move an axis, switch a relay.

Syndesi answers each question with a separate layer.

.. raw:: html

   <div class="sy-stack">
     <div class="sy-layer sy-driver">
       <span class="sy-layer-name">Driver</span>
       <span class="sy-layer-items">psu.channel(1).set_voltage(3.3)</span>
       <span class="sy-layer-type">what the device does</span>
     </div>
     <div class="sy-layer sy-protocol">
       <span class="sy-layer-name">Protocol</span>
       <span class="sy-layer-items">"INST:NSEL 1;VOLT 3.3"</span>
       <span class="sy-layer-type">what messages look like</span>
     </div>
     <div class="sy-layer sy-adapter">
       <span class="sy-layer-name">Adapter</span>
       <span class="sy-layer-items">b"INST:NSEL 1;VOLT 3.3\n"</span>
       <span class="sy-layer-type">how bytes travel</span>
     </div>
     <div class="sy-device">▼ POWER SUPPLY</div>
   </div>

Adapters
--------

An adapter moves **bytes** between your program and a device: ``IP``, ``SerialPort``,
``Visa``, ``IPServer``. On top of moving them, it answers the hardest question of the
receiving side: *when is a message complete?* That is the job of its stop conditions
(see :doc:`frames`).

An adapter knows nothing of the meaning of the bytes. It is the right layer for
binary devices with no standard protocol, or to explore a device you don't know yet.

Protocols
---------

A protocol sits on an adapter and gives messages their shape: ``Delimited`` adds and
removes terminators and works with ``str``, ``SCPI`` follows instrument conventions,
``Modbus`` builds and checks binary frames and exposes ``read_holding_registers()``.

A protocol also configures the adapter below it. ``Delimited`` sets a ``Termination``
stop condition, ``Modbus`` the port 502, ``SCPI`` the port 5025. This is why
``SCPI(IP("192.168.1.42"))`` is enough: every setting a protocol can decide, it decides,
unless you did first.

Drivers
-------

A driver describes **one kind of device**, with methods named after what it does:
``set_voltage``, ``measure_dc_voltage``, ``temperature``. It builds on a protocol (or
an adapter), and hides it.

Drivers are where reuse happens. Your test scripts depend on ``PowerSupply``, not on
``"VOLT 3.3"``, and they don't depend on the cable either: the same driver works over
``IP`` or ``SerialPort``.

Drivers compose:

- a **sub-driver** is a part of a device (a channel, an axis) that uses its parent's
  connection;
- a driver can be built on other drivers, like a test bench made of a power supply and
  a multimeter;
- a **bridge** is a driver that *provides* a bus (I2C, SPI, UART) to the layers above
  it, so sensor drivers don't depend on the converter board.

Choosing a layer
----------------

==================================================  ===========================
You want to…                                        Use
==================================================  ===========================
explore an unknown device, or speak binary           an adapter (``IP``…)
send text commands to a firmware                     ``Delimited``
control a lab instrument                             ``SCPI``, then a driver
read a PLC or a meter                                ``Modbus``
write test scripts that last                         a driver
==================================================  ===========================

You can mix them: a driver may use ``write_raw`` on its protocol, and a protocol's
``adapter`` attribute gives access to the adapter below.
