Use the interactive terminal
============================

``syndesi term`` opens a console connected to a device: type a command, press
:kbd:`Enter`, read the answer. History, search and auto-suggestion included.

Open a terminal
---------------

.. code-block:: console

   $ syndesi term ip 192.168.1.10 5025
   $ syndesi term ip 192.168.1.50 9000 --protocol UDP
   $ syndesi term serial /dev/ttyUSB0 115200
   $ syndesi term serial COM3 9600 --rtscts
   $ syndesi term visa "USB0::0x2A8D::0x1301::MY59001234::INSTR"

Find the serial ports
---------------------

.. code-block:: console

   $ syndesi term serial --list
   /dev/ttyUSB0  CP2102 USB to UART Bridge Controller
   /dev/ttyACM0  Arduino Uno

The description comes from the system, when it knows what is plugged in. The same
works for buses: ``syndesi term i2c --list``, ``syndesi term spi --list``.

Choose the line ending
----------------------

Each command is sent with ``\n`` by default:

.. code-block:: console

   $ syndesi term serial /dev/ttyUSB0 9600 --term crlf   # cr, lf, crlf, or any string

Send and display binary data
----------------------------

.. code-block:: console

   $ syndesi term ip 10.0.0.7 4000 -f hex

With ``-f hex``, type bytes as hex (``aa 01 00 ff`` or ``aa0100ff``), and answers are
shown in hex. ``-f bytes`` (default) uses the Python ``b'...'`` notation, ``-f raw``
shows text as is.

Wait longer for answers
-----------------------

.. code-block:: console

   $ syndesi term ip 192.168.1.10 5025 -t 10

All options are listed in :doc:`/reference/cli`.
