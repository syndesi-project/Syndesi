Write your first driver
=======================

A **driver** is a Python class that turns a device's commands into methods with
meaningful names. Instead of ``psu.write("INST:NSEL 2;VOLT 12")`` your test scripts will
read ``psu.channel(2).set_voltage(12)``.

In this tutorial you will write a driver for the simulated power supply of the
:doc:`previous tutorial <scpi-instrument>`, then use it from a script and from the
graphical bench.

.. rubric:: What you need

The simulated power supply running, as in :doc:`scpi-instrument`:

.. code-block:: console

   $ python fake_psu.py

Start from SCPIDriver
---------------------

Syndesi ships ``SCPIDriver``, a base class that already knows the commands every SCPI
instrument shares (``*IDN?``, ``*RST``, ``SYST:ERR?``…). It creates the ``SCPI``
protocol for you and stores it in ``self._prot``.

Create ``power_supply.py``:

.. code-block:: python
   :caption: power_supply.py

   from syndesi import SCPIDriver


   class PowerSupply(SCPIDriver):
       """A two-channel lab power supply"""

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return "DemoPSU" in self.get_identification()

``open``, ``close`` and ``test`` are the three methods every driver provides. ``test``
answers a simple question: *am I talking to the right device?*

Try it:

.. code-block:: python

   >>> from syndesi import IP
   >>> from power_supply import PowerSupply
   >>> psu = PowerSupply(IP("127.0.0.1"))
   >>> psu.test()
   True
   >>> psu.get_identification()
   'Syndesi,DemoPSU,0001,1.0'

You already have the standard SCPI commands, for free.

Add your own methods
--------------------

Now the commands specific to this power supply. Add them to the class:

.. code-block:: python
   :caption: power_supply.py

   from syndesi import SCPIDriver


   class PowerSupply(SCPIDriver):
       """A two-channel lab power supply"""

       def set_voltage(self, volts: float) -> None:
           """Set the output voltage, in volts"""
           self._prot.write(f"VOLT {volts}")

       def measure_voltage(self) -> float:
           """Voltage measured at the output, in volts"""
           return float(self._prot.query("MEAS:VOLT?"))

       def set_output(self, enabled: bool) -> None:
           """Switch the output on or off"""
           self._prot.write(f"OUTP {'ON' if enabled else 'OFF'}")

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return "DemoPSU" in self.get_identification()

Each method is two lines: build the command, send it. Type hints and docstrings are not
decoration: the graphical bench uses them to build its forms, as you will see below.

One object per channel
----------------------

Our instrument has two outputs. Rather than passing a channel number to every method,
give each output its own object. A part of a device that has methods but no connection
of its own is a ``SubDriver``:

.. code-block:: python
   :caption: power_supply.py

   from typing import Any

   from syndesi import Adapter, SCPIDriver, SubDriver
   from syndesi.protocols.scpi import SCPI


   class Channel(SubDriver):
       """One output of the power supply"""

       def __init__(self, protocol: SCPI, number: int) -> None:
           self._prot = protocol
           self.number = number

       def _select(self) -> str:
           return f"INST:NSEL {self.number};"

       def set_voltage(self, volts: float) -> None:
           """Set the output voltage, in volts"""
           self._prot.write(f"{self._select()}VOLT {volts}")

       def measure_voltage(self) -> float:
           """Voltage measured at the output, in volts"""
           return float(self._prot.query(f"{self._select()}MEAS:VOLT?"))

       def set_output(self, enabled: bool) -> None:
           """Switch the output on or off"""
           self._prot.write(f"{self._select()}OUTP {'ON' if enabled else 'OFF'}")


   class PowerSupply(SCPIDriver):
       """A two-channel lab power supply"""

       def __init__(self, adapter: Adapter[Any, bytes]) -> None:
           super().__init__(adapter)
           self.channels = [Channel(self._prot, 1), Channel(self._prot, 2)]

       def channel(self, number: int) -> Channel:
           """Return one output, numbered from 1"""
           return self.channels[number - 1]

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return "DemoPSU" in self.get_identification()

Use it in a script
------------------

.. code-block:: python
   :caption: bench.py

   from syndesi import IP
   from power_supply import PowerSupply

   psu = PowerSupply(IP("127.0.0.1"))
   psu.open()
   try:
       rail = psu.channel(1)
       rail.set_voltage(3.3)
       rail.set_output(True)
       print(f"3V3 rail: {rail.measure_voltage():.3f} V")
       rail.set_output(False)
   finally:
       psu.close()

.. code-block:: console

   $ python bench.py
   3V3 rail: 3.301 V

``open()`` fails right away if the instrument is unreachable, and ``finally`` makes
sure the connection is closed even if a step fails.

.. note::

   The driver doesn't care how the instrument is connected. Over a serial cable, the
   same class works with ``PowerSupply(SerialPort("/dev/ttyUSB0", 9600))``.

Open it in the graphical bench
------------------------------

The graphical interface needs the ``ui`` extra:

.. code-block:: console

   $ pip install "syndesi[ui]"
   $ syndesi ui -l power_supply.py:PowerSupply

``-l`` adds the classes of your file to the library, and ``:PowerSupply`` puts it on
top of the stack. Drop an ``IP`` adapter in its slot, set the address to
``127.0.0.1``, and open the *Test* screen: every method you wrote is there, with a form
built from its type hints, ready to run.

What you learned
----------------

- A driver is a class built on a protocol (or an adapter), with methods named after
  what the device does.
- ``SCPIDriver`` gives you the standard SCPI commands and a ready ``self._prot``.
- ``SubDriver`` models a part of a device, like a channel.
- Drivers work with any adapter, and the graphical bench can drive them without extra
  code.

.. container:: sd-text-right

   :doc:`Next: a Modbus device in five minutes → <modbus-loopback>`
