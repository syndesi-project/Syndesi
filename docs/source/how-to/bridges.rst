Use I2C, SPI and GPIO
=====================

Sensors, ADCs, EEPROMs and displays hang on an I2C or SPI bus. ``I2C`` and ``SPI`` are
adapters for one device on such a bus, whatever provides it: the machine itself
(Raspberry Pi…), a USB converter like the MCP2221, or a board of your own. What provides
the bus is a **bridge**.

.. code-block:: text

   TMP102 driver                    ← knows the sensor, not the bus
     └ I2C(address=0x48)
        └ MCP2221  (bridge)         ← knows the converter, not the sensor
           └ HID(0x04D8, 0x00DD)

I2C on the machine (Linux)
--------------------------

.. code-block:: python

   from syndesi import I2C

   sensor = I2C("/dev/i2c-1", 0x48)
   sensor.write(b"\x01\x60\xa0")                    # write register 1
   sensor.transfer(b"\x00", read_length=2)          # read 2 bytes from register 0
   sensor.transfer(read_length=2)                   # plain read

``transfer`` writes, then reads with a repeated start. ``I2C.list_buses()`` lists the
buses. The ``i2c-dev`` kernel module and access to ``/dev/i2c-*`` are needed.

SPI on the machine (Linux)
--------------------------

.. code-block:: python

   from syndesi import SPI

   flash = SPI("/dev/spidev0.0", mode=0, speed_hz=1_000_000)
   jedec_id = flash.transfer(b"\x9f\x00\x00\x00")[1:]   # bytes received meanwhile
   flash.write(b"\x06")                                 # answer ignored

I2C and GPIO through an MCP2221
-------------------------------

The Microchip MCP2221 (and MCP2221A) turns a USB port into an I2C bus and four GPIOs.
It is a HID device, so it works on Linux, Windows and macOS without a driver. Install
the HID support first (see :doc:`hid`):

.. code-block:: console

   $ pip install "syndesi[hid]"

Then use its bus like any other:

.. code-block:: python

   from syndesi import I2C, MCP2221

   mcp = MCP2221()                                  # the first MCP2221 connected
   sensor = I2C(mcp, 0x48)
   sensor.transfer(b"\x00", read_length=2)

   mcp.set_i2c_speed(400_000)                       # 100 kHz by default

Several ``I2C`` adapters can share the bridge, one per address. Their transfers run one
at a time.

A device that doesn't answer raises ``AdapterWriteError`` ("address not
acknowledged").

The GPIOs:

.. code-block:: python

   mcp.configure_gpio(0, output=True)       # GP0 as an output, low
   mcp.set_gpio(0, True)

   mcp.configure_gpio(1, output=False)      # GP1 as an input
   mcp.get_gpio(1)                          # True
   mcp.get_gpios()                          # [True, True, None, None], None: not a GPIO

The configuration lasts until the chip is unplugged or reset.

Several chips: ``MCP2221(serial_number="...")`` (the serial number has to be enabled in
the chip first), or pass the HID adapter yourself, ``MCP2221(HID(path=...))``.

.. note::

   The UART of the MCP2221 is a separate USB serial port: open it with
   ``SerialPort("/dev/ttyACM0", 9600)`` (``COM5`` on Windows).

Write a bridge for your own board
---------------------------------

A bridge is a driver that also inherits ``I2CBridge``, ``SPIBridge`` and/or
``SerialBridge``, and implements their methods with ordinary blocking code. Say your
board answers commands like ``I2C 48 0100 2`` (address, data to write, bytes to read)
with ``OK:60a0``:

.. code-block:: python

   from syndesi import Delimited, Driver, I2CBridge, SPIBridge

   class MyBoard(Driver, I2CBridge, SPIBridge):
       def __init__(self, adapter) -> None:
           super().__init__()
           self._prot = Delimited(adapter)

       def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
           answer = self._prot.query(f"I2C {address:02x} {data.hex() or '-'} {read_length}")
           return bytes.fromhex(answer.removeprefix("OK:"))

       def spi_transfer(self, cs: int, data: bytes) -> bytes:
           answer = self._prot.query(f"SPI {cs} {data.hex()}")
           return bytes.fromhex(answer.removeprefix("OK:"))

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return self._prot.query("ID?") == "MYBOARD"

.. code-block:: python

   board = MyBoard(SerialPort("/dev/ttyUSB0", 115200))
   sensor = I2C(board, 0x48)
   flash = SPI(board, cs=1)

Each bridge runs its methods on its own thread, one at a time: they can block, and need
no lock. The SPI mode and clock of a bridge's bus are settings of its driver.

Provide a serial port
---------------------

A board that forwards a UART implements ``SerialBridge``. Pass it to ``SerialPort``
instead of a port name, and protocols work on top of it as on any serial port:

.. code-block:: python

   class MyBoard(Driver, SerialBridge):
       def serial_configure(self, baudrate, bytesize, parity, stopbits) -> None:
           self._prot.query(f"UART CFG {baudrate} {bytesize}{parity}{stopbits}")

       def serial_write(self, data: bytes) -> None:
           self._prot.query(f"UART W {data.hex()}")

       def serial_read(self, timeout: float) -> bytes:
           return bytes.fromhex(self._prot.query("UART R").removeprefix("OK:"))
       ...

   gps = Delimited(SerialPort(board, 9600), "\r\n")

``serial_read`` is called in a loop while the port is open. Return ``b""`` when nothing
came.

Write a driver for the chip
---------------------------

Your sensor driver only needs an ``I2C``, whatever provides the bus:

.. code-block:: python

   class TMP102(Driver):
       def __init__(self, bus: I2C) -> None:
           super().__init__()
           self._bus = bus

       def temperature(self) -> float:
           raw = int.from_bytes(self._bus.transfer(b"\x00", read_length=2), "big") >> 4
           return raw * 0.0625
       ...

   TMP102(I2C("/dev/i2c-1", 0x48)).temperature()   # on a Raspberry Pi
   TMP102(I2C(MCP2221(), 0x48)).temperature()      # through USB
