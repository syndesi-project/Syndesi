Reach I2C, SPI and UART through a board
=======================================

Sensors and chips often hang on an I2C or SPI bus, reached through a converter: an
MCP2221, an FTDI chip, a custom microcontroller board… A **bridge** is the driver of
that converter. It provides the bus, and ``I2C``, ``SPI`` or ``SerialPort`` objects use
it, so the drivers of your sensors don't depend on the converter.

.. code-block:: text

   TemperatureSensor driver         ← knows the sensor, not the board
     └ I2C(address=0x48)
        └ MyBoard  (I2CBridge)      ← knows the board, not the sensor
           └ Delimited(SerialPort("/dev/ttyUSB0", 115200))

Write a bridge
--------------

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

Talk to an I2C device
---------------------

.. code-block:: python

   from syndesi import I2C, SerialPort

   board = MyBoard(SerialPort("/dev/ttyUSB0", 115200))
   sensor = I2C(board, address=0x48)

   sensor.write(b"\x01\x60\xa0")        # write register 1
   sensor.write_read(b"\x00", 2)        # read 2 bytes from register 0
   sensor.read(2)                       # plain read

Several ``I2C`` objects can share a bridge, one per address. Their calls are run one at
a time, no lock needed.

Talk to an SPI device
---------------------

.. code-block:: python

   from syndesi import SPI

   flash = SPI(board, cs=0)
   jedec_id = flash.transfer(b"\x9f\x00\x00\x00")[1:]
   flash.write(b"\x06")                 # write enable, answer ignored

The SPI mode and clock are settings of the board, configured by its driver.

Provide a serial port
---------------------

A board that forwards a UART implements ``SerialBridge``. Pass it to ``SerialPort``
instead of a port name, and protocols work on top of it as on any serial port:

.. code-block:: python

   from syndesi import Delimited, SerialBridge, SerialPort

   class MyBoard(Driver, SerialBridge):
       def serial_configure(self, baudrate, bytesize, parity, stopbits) -> None:
           self._prot.query(f"UART CFG {baudrate} {bytesize}{parity}{stopbits}")

       def serial_write(self, data: bytes) -> None:
           self._prot.query(f"UART W {data.hex()}")

       def serial_read(self, timeout: float) -> bytes:
           return bytes.fromhex(self._prot.query("UART R").removeprefix("OK:"))
       ...

   gps = Delimited(SerialPort(board, 9600), "\r\n")
   gps.read()   # '$GPGGA,123519,4807.038,N,...'

``serial_read`` is called in a loop while the port is open. Return ``b""`` when nothing
came.

Write a driver for the chip
---------------------------

Your sensor driver only needs an ``I2C``, whatever board provides it:

.. code-block:: python

   class TMP102(Driver):
       def __init__(self, bus: I2C) -> None:
           super().__init__()
           self._bus = bus

       def temperature(self) -> float:
           raw = int.from_bytes(self._bus.write_read(b"\x00", 2), "big") >> 4
           return raw * 0.0625
       ...

   TMP102(I2C(board, 0x48)).temperature()   # 23.4375
