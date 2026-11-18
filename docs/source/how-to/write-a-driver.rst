Write a driver
==============

A driver is a class with methods named after what the device does. It owns its
protocol (or adapter) and implements ``open``, ``close`` and ``test``.

.. seealso::

   :doc:`/tutorials/first-driver` builds a driver step by step.

A driver for a SCPI instrument
------------------------------

Subclass ``SCPIDriver``: you get the ``*IDN?``, ``*RST``… methods and a ``SCPI``
protocol in ``self._prot``.

.. code-block:: python

   from syndesi import SCPIDriver

   class Multimeter(SCPIDriver):
       def measure_dc_voltage(self) -> float:
           """DC voltage, in volts"""
           return float(self._prot.query("MEAS:VOLT:DC?"))

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return "34465A" in self.get_identification()

.. code-block:: python

   dmm = Multimeter(IP("192.168.1.20"))
   dmm.measure_dc_voltage()   # 4.9987

A driver for any other device
-----------------------------

Subclass ``Driver`` and build the protocol you need:

.. code-block:: python

   from typing import Any

   from syndesi import Adapter, Delimited, Driver

   class Thermometer(Driver):
       def __init__(self, adapter: Adapter[Any, bytes]) -> None:
           super().__init__()
           self._prot = Delimited(adapter, "\r\n")

       def temperature(self) -> float:
           """Temperature, in °C"""
           return float(self._prot.query("T?"))

       def open(self) -> None:
           self._prot.open()

       def close(self) -> None:
           self._prot.close()

       def test(self) -> bool:
           return self._prot.query("ID?").startswith("THERMO")

.. _driver-any-adapter:

Accept an adapter or a string
-----------------------------

With ``auto_adapter``, users can pass ``"192.168.1.20:5025:TCP"`` or
``"/dev/ttyUSB0:9600"`` instead of building the adapter:

.. code-block:: python

   from syndesi import Adapter, Driver, auto_adapter

   class Thermometer(Driver):
       def __init__(self, adapter: Adapter[Any, bytes] | str) -> None:
           super().__init__()
           self._prot = Delimited(auto_adapter(adapter), "\r\n")

Set the device's defaults
-------------------------

A driver often knows the baudrate or port of its device. The ``set_default_*`` methods
apply them only if the user didn't choose another value:

.. code-block:: python

   def __init__(self, adapter):
       super().__init__()
       if isinstance(adapter, SerialPort):
           adapter.set_default_baudrate(115200)
       elif isinstance(adapter, IP):
           adapter.set_default_port(4000)
       adapter.set_default_timeout(5)
       self._prot = Delimited(adapter)

Split a device into parts
-------------------------

Channels, outputs, axes… A ``SubDriver`` is a part of a device: it has methods but no
connection of its own, it uses its parent's.

.. code-block:: python

   from syndesi import SCPIDriver, SubDriver

   class Output(SubDriver):
       def __init__(self, prot, number: int) -> None:
           self._prot = prot
           self.number = number

       def set_voltage(self, volts: float) -> None:
           self._prot.write(f"INST:NSEL {self.number};VOLT {volts}")

   class PowerSupply(SCPIDriver):
       def __init__(self, adapter) -> None:
           super().__init__(adapter)
           self.outputs = [Output(self._prot, n) for n in (1, 2, 3)]
       ...

   psu.outputs[0].set_voltage(3.3)

Build a driver on other drivers
-------------------------------

A test bench is a driver too, made of the instruments it uses:

.. code-block:: python

   class Bench(Driver):
       def __init__(self, psu: PowerSupply, dmm: Multimeter) -> None:
           super().__init__()
           self.psu, self.dmm = psu, dmm

       def power_up(self) -> float:
           self.psu.outputs[0].set_voltage(3.3)
           return self.dmm.measure_dc_voltage()

       def open(self) -> None:
           self.psu.open()
           self.dmm.open()

       def close(self) -> None:
           self.psu.close()
           self.dmm.close()

       def test(self) -> bool:
           return self.psu.test() and self.dmm.test()

Make it shine in the graphical bench
------------------------------------

``syndesi ui`` builds its forms from your code: annotate the parameters and return
values, and write a docstring with a numpy-style ``Parameters`` section. See
:doc:`gui`.
