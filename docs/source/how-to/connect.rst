Connect to a device
===================

Pick the adapter that matches the cable. They all share the same methods: ``write``,
``read``, ``query``, ``open`` and ``close``.

Over the network (TCP)
----------------------

.. code-block:: python

   from syndesi import IP

   dev = IP("192.168.1.10", 5025)
   dev.query(b"*IDN?\n")

Host names work too: ``IP("scope-lab3.local", 5025)``.

Over the network (UDP)
----------------------

.. code-block:: python

   from syndesi import IP

   dev = IP("192.168.1.50", 9000, "UDP")
   dev.write(b"\x01\x02")
   dev.read()

Over a serial port
------------------

.. code-block:: python

   from syndesi import SerialPort

   port = SerialPort("/dev/ttyUSB0", 115200)   # "COM3" on Windows
   port.query(b"status\n")

Line settings are keyword arguments:

.. code-block:: python

   from syndesi import Parity, SerialPort

   port = SerialPort(
       "COM4", 9600,
       bytesize=7, parity=Parity.EVEN, stopbits=2,
       rts_cts=True,   # hardware flow control, also xon_xoff and dsr_dtr
   )

List the serial ports
---------------------

.. code-block:: python

   >>> SerialPort.list_ports()
   ['/dev/ttyUSB0', '/dev/ttyACM0']

Or from the command line: ``syndesi term serial --list``.

Through VISA (USB-TMC, GPIB, LXI)
---------------------------------

VISA needs the optional ``pyvisa`` dependency, and a VISA backend such as NI-VISA,
Keysight IO Libraries or ``pyvisa-py``:

.. code-block:: console

   $ pip install "syndesi[visa]"

.. code-block:: python

   from syndesi import Visa

   Visa.list_devices()   # ['USB0::0x2A8D::0x1301::MY59001234::INSTR', ...]

   dmm = Visa("USB0::0x2A8D::0x1301::MY59001234::INSTR")
   dmm.query(b"*IDN?\n")

Usual resource names:

=========================  ==========================================
GPIB                       ``GPIB0::14::INSTR``
USB-TMC                    ``USB0::0x0957::0x1796::MY12345678::INSTR``
LXI / VXI-11 / HiSLIP      ``TCPIP0::192.168.1.100::INSTR``
Raw socket                 ``TCPIP0::192.168.1.42::5025::SOCKET``
Serial                     ``ASRL/dev/ttyUSB0::INSTR``, ``ASRL1::INSTR``
=========================  ==========================================

.. tip::

   A SCPI instrument on the network doesn't need VISA: ``SCPI(IP("192.168.1.42"))``
   talks to it directly, with no driver to install.

From a string
-------------

``auto_adapter`` builds the adapter a string describes. It is handy in configuration
files and command line options:

.. code-block:: python

   from syndesi import auto_adapter

   auto_adapter("192.168.1.10:5025:TCP")     # IP
   auto_adapter("192.168.1.50:9000:UDP")     # IP over UDP
   auto_adapter("/dev/ttyUSB0:115200")       # SerialPort
   auto_adapter("COM3:9600")                 # SerialPort
   auto_adapter("GPIB0::14::INSTR")          # Visa (if pyvisa is installed)

Given an adapter instead of a string, it returns it unchanged. See
:ref:`driver-any-adapter` to use it in a driver.

Open early, or not at all
-------------------------

Adapters open on the first operation. To fail right away if the device is unreachable,
open explicitly:

.. code-block:: python

   dev = IP("192.168.1.10", 5025)
   dev.open()   # raises AdapterOpenError now, not at the first query

To open and close around a block, use ``with``:

.. code-block:: python

   with IP("192.168.1.10", 5025) as dev:
       dev.write(b"*RST\n")

Once closed, an adapter only reopens with an explicit ``open()``.

Wait longer for answers
-----------------------

Each adapter waits a limited time for an answer: 1 s for ``IP``, 2 s for
``SerialPort``, 5 s for ``Visa``. Change it at creation, or for a single call:

.. code-block:: python

   dev = IP("192.168.1.10", 5025, timeout=10)
   dev.query(b"MEAS?\n", timeout=30)   # this call only
   dev.query(b"WAIT\n", timeout=None)  # wait forever

.. note::

   When a protocol is stacked on an adapter (``SCPI(IP(...))``), set the timeout on the
   **adapter**, when you create it: the protocol uses it too. See
   :ref:`timeouts`.

Name it
-------

``alias`` gives an adapter a readable name in logs and in ``syndesi-trace``:

.. code-block:: python

   psu = IP("192.168.1.30", 5025, alias="psu")
