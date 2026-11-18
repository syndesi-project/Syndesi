Control SCPI instruments
========================

``SCPI`` is ``Delimited`` with the conventions of lab instruments: port 5025 on the
network and ``\n`` as terminator.

Over the network
----------------

.. code-block:: python

   from syndesi import IP, SCPI

   dmm = SCPI(IP("192.168.1.20"))        # port 5025 by default
   dmm.query("*IDN?")
   volts = float(dmm.query("MEAS:VOLT:DC?"))

Over USB, GPIB or serial
------------------------

.. code-block:: python

   from syndesi import SCPI, SerialPort, Visa

   SCPI(Visa("USB0::0x2A8D::0x1301::MY59001234::INSTR"))
   SCPI(Visa("GPIB0::14::INSTR"))
   SCPI(SerialPort("/dev/ttyUSB0", 9600))

Standard commands
-----------------

``SCPIDriver`` already implements the IEEE-488.2 common commands. Subclass it for your
instrument (see :doc:`write-a-driver`), or use them as is:

=============================  ============
``get_identification()``       ``*IDN?``
``reset()``                    ``*RST``
``clear_status_registers()``   ``*CLS``
``trigger()``                  ``*TRG``
``get_system_error()``         ``SYST:ERR?``
``get_system_version()``       ``SYST:VERS?``
=============================  ============

Slow measurements
-----------------

Give the adapter a timeout long enough for the slowest command:

.. code-block:: python

   scope = SCPI(IP("192.168.1.42", timeout=10))

Another terminator
------------------

Some instruments, often over serial, use ``\r\n``:

.. code-block:: python

   SCPI(SerialPort("COM5", 115200), termination="\r\n")

.. note::

   ``SCPI`` sets the adapter's stop conditions from its terminator, so the adapter must
   be created without ``stop_conditions``.

Binary blocks
-------------

To send a block without the terminator (arbitrary waveform data…):

.. code-block:: python

   awg.write_raw(b"#3512" + samples)                 # no terminator
   awg.write_raw(b"#3512" + samples, termination=True)  # with it
