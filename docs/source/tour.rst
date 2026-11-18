A tour of Syndesi
=================

Everything Syndesi can do, one tiny example at a time. Each card links to the guide
that goes further.

Connect
-------

.. grid:: 1 1 2 2
   :gutter: 3
   :class-container: sy-tour

   .. grid-item-card:: TCP

      .. code-block:: python

         from syndesi import IP

         dev = IP("192.168.1.10", 5025)
         dev.query(b"*IDN?\n")   # b'ACME,PSU-3000,...\n'

      .. card-footer::

         :doc:`how-to/connect`

   .. grid-item-card:: UDP

      .. code-block:: python

         from syndesi import IP

         sensor = IP("192.168.1.50", 9000, "UDP")
         sensor.write(b"START")

      .. card-footer::

         :doc:`how-to/connect`

   .. grid-item-card:: Serial port

      .. code-block:: python

         from syndesi import SerialPort

         arduino = SerialPort("/dev/ttyUSB0", 115200)  # COM3 on Windows
         arduino.query(b"temp?\n")   # b'21.5\n'

      .. card-footer::

         :doc:`how-to/connect`

   .. grid-item-card:: VISA (USB, GPIB, LXI)

      .. code-block:: python

         from syndesi import Visa

         dmm = Visa("USB0::0x2A8D::0x1301::MY5900::INSTR")
         dmm.query(b"MEAS:VOLT:DC?\n")

      .. card-footer::

         :doc:`how-to/connect`

   .. grid-item-card:: From a string

      .. code-block:: python

         from syndesi import auto_adapter

         auto_adapter("192.168.1.10:5025:TCP")  # IP
         auto_adapter("/dev/ttyUSB0:115200")    # SerialPort

      .. card-footer::

         :doc:`how-to/connect`

   .. grid-item-card:: Context manager

      .. code-block:: python

         from syndesi import IP

         with IP("192.168.1.10", 5025) as dev:
             dev.write(b"*RST\n")
         # closed here

      .. card-footer::

         :doc:`how-to/connect`

Frame messages
--------------

.. grid:: 1 1 2 2
   :gutter: 3
   :class-container: sy-tour

   .. grid-item-card:: Stop on a terminator

      .. code-block:: python

         from syndesi import SerialPort, Termination

         port = SerialPort("COM3", 9600,
                           stop_conditions=Termination(b"\r\n"))

      .. card-footer::

         :doc:`how-to/framing`

   .. grid-item-card:: Fixed-size packets

      .. code-block:: python

         from syndesi import IP, Length

         dev = IP("10.0.0.7", 4000, stop_conditions=Length(16))
         packet = dev.read()   # exactly 16 bytes

      .. card-footer::

         :doc:`how-to/framing`

   .. grid-item-card:: Stop on silence

      .. code-block:: python

         from syndesi import SerialPort, Continuation

         # Done when nothing arrived for 50 ms
         port = SerialPort("/dev/ttyACM0", 115200,
                           stop_conditions=Continuation(0.05))

      .. card-footer::

         :doc:`how-to/framing`

   .. grid-item-card:: Know how it ended

      .. code-block:: python

         frame = dev.query_detailed(b"PING\n")
         frame.data             # b'PONG\n'
         frame.stop_condition   # Termination(b'\n')
         frame.response_delay   # 0.0012 s

      .. card-footer::

         :doc:`explanation/frames`

Speak a protocol
----------------

.. grid:: 1 1 2 2
   :gutter: 3
   :class-container: sy-tour

   .. grid-item-card:: Text commands

      .. code-block:: python

         from syndesi import Delimited, SerialPort

         board = Delimited(SerialPort("/dev/ttyUSB0", 115200))
         board.query("version")   # 'v1.4.2', '\n' added and removed

      .. card-footer::

         :doc:`how-to/text-commands`

   .. grid-item-card:: SCPI instruments

      .. code-block:: python

         from syndesi import IP, SCPI

         dmm = SCPI(IP("192.168.1.20"))       # port 5025
         float(dmm.query("MEAS:VOLT:DC?"))    # 4.9987

      .. card-footer::

         :doc:`how-to/scpi`

   .. grid-item-card:: Modbus TCP

      .. code-block:: python

         from syndesi import IP, Modbus

         plc = Modbus(IP("192.168.1.100"))    # port 502
         plc.read_holding_registers(1, 4)     # [12, 0, 450, 7]
         plc.write_single_coil(3, True)

      .. card-footer::

         :doc:`how-to/modbus-client`

   .. grid-item-card:: Modbus RTU

      .. code-block:: python

         from syndesi import Modbus, SerialPort

         meter = Modbus(SerialPort("/dev/ttyUSB0", 19200),
                        slave_address=1)
         meter.read_input_registers(1, 2)

      .. card-footer::

         :doc:`how-to/modbus-client`

   .. grid-item-card:: Floats, strings and 32-bit integers

      .. code-block:: python

         value = plc.read_multi_register_value(10, 2)
         value.to_float()   # 21.5
         value.to_uint()    # 1101791232

      .. card-footer::

         :doc:`how-to/modbus-client`

   .. grid-item-card:: Be a Modbus device

      .. code-block:: python

         from syndesi import IPServer, ModbusServer

         server = ModbusServer(IPServer("0.0.0.0"))
         server.holding_registers[1] = 1234
         server.serve_forever()

      .. card-footer::

         :doc:`how-to/modbus-server`

Go further
----------

.. grid:: 1 1 2 2
   :gutter: 3
   :class-container: sy-tour

   .. grid-item-card:: Async

      .. code-block:: python

         from syndesi import AsyncIP, AsyncSCPI

         async def identify(address):
             dmm = AsyncSCPI(AsyncIP(address))
             return await dmm.query("*IDN?")

      .. card-footer::

         :doc:`how-to/async`

   .. grid-item-card:: Your own driver

      .. code-block:: python

         class PowerSupply(SCPIDriver):
             def set_voltage(self, volts: float) -> None:
                 self._prot.write(f"VOLT {volts}")

         PowerSupply(IP("192.168.1.30")).set_voltage(3.3)

      .. card-footer::

         :doc:`how-to/write-a-driver`

   .. grid-item-card:: TCP server

      .. code-block:: python

         from syndesi import IPServer

         server = IPServer("0.0.0.0", 8888)
         client = server.read()   # an IP adapter
         client.write(b"Welcome\n")

      .. card-footer::

         :doc:`how-to/ip-server`

   .. grid-item-card:: I2C and SPI through a bridge

      .. code-block:: python

         from syndesi import I2C

         sensor = I2C(my_board, address=0x48)
         raw = sensor.write_read(b"\x00", 2)  # register 0

      .. card-footer::

         :doc:`how-to/bridges`

   .. grid-item-card:: Watch the traffic

      .. code-block:: console

         $ syndesi-trace

      Every byte sent or received by any Syndesi script on this machine, live.

      .. card-footer::

         :doc:`how-to/debugging`

   .. grid-item-card:: Interactive terminal

      .. code-block:: console

         $ syndesi term ip 192.168.1.10 5025
         ❯ *IDN?

      .. card-footer::

         :doc:`how-to/terminal`
