Buses and bridges
=================

Devices on an I2C or SPI bus, and the bridges that provide the bus. Guide:
:doc:`/how-to/bridges`.

Bus adapters
------------

.. autoclass:: syndesi.adapters.i2c.I2C
   :members: transfer, list_buses
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.i2c.I2CTransfer
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.spi.SPI
   :members: transfer, list_buses
   :no-show-inheritance:

``AsyncI2C`` and ``AsyncSPI`` take the same parameters. A ``SerialPort`` takes a
``SerialBridge`` in place of a port name, see
:class:`~syndesi.adapters.serialport.SerialPort`.

Bridges
-------

.. autoclass:: syndesi.bridges.mcp2221.MCP2221
   :members: set_i2c_speed, i2c_speed, configure_gpio, set_gpio, get_gpio, get_gpios,
             reset
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.linux.LinuxI2C
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.bridges.linux.LinuxSPI
   :no-members:
   :no-show-inheritance:

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
   :members: run, close_bridge, bridge_name, set_bridge_name
   :no-show-inheritance:
