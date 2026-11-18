Bridges
=======

Bus devices, and the bridges that provide their bus. Guide: :doc:`/how-to/bridges`.

Bus devices
-----------

.. autoclass:: syndesi.bridges.i2c.I2C
   :members: write, read, write_read
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.spi.SPI
   :members: transfer, write
   :no-show-inheritance:

A ``SerialPort`` takes a ``SerialBridge`` in place of a port name, see
:class:`~syndesi.adapters.serialport.SerialPort`.

Bridge interfaces
-----------------

Inherit one or more of these in your board's driver and implement their methods.

.. autoclass:: syndesi.bridges.bridge.I2CBridge
   :members: i2c_transfer
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.bridge.SPIBridge
   :members: spi_transfer
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.bridge.SerialBridge
   :members: serial_configure, serial_write, serial_read, SERIAL_POLL_PERIOD
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.bridge.Bridge
   :members: run, close_bridge
   :no-show-inheritance:
