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

Set the device's defaults
-------------------------

A driver often knows the baudrate, port or timeout of its device. The ``set_default_*``
methods apply them only if the user didn't choose another value. A protocol built
afterwards adopts the default timeout of the driver:

.. code-block:: python

   def __init__(self, adapter):
       super().__init__()
       if isinstance(adapter, SerialPort):
           adapter.set_default_baudrate(115200)
       elif isinstance(adapter, IP):
           adapter.set_default_port(4000)
       adapter.set_default_timeout(5)
       self._prot = Delimited(adapter)

Accept what the user writes
---------------------------

Ranges, functions, speeds… A device wants one exact value, a user writes ``2``,
``"2V"`` or ``"2 v"``. A ``FlexibleEnum`` member is the value sent to the device,
followed by the values it accepts:

.. code-block:: python

   from syndesi import FlexibleEnum, SCPIDriver

   class VoltageRange(FlexibleEnum):
       _200mV = "0.2", 0.2, "200mV"
       _2V = "2", 2, "2V"
       _20V = "20", 20, "20V"
       AUTO = "AUTO"

   class Multimeter(SCPIDriver):
       def set_voltage_range(self, voltage_range: VoltageRange | str | float) -> None:
           self._prot.write(f"VOLT:RANG {VoltageRange(voltage_range)}")

       def voltage_range(self) -> VoltageRange:
           # The device replies '+2.000000E-01' : a number, it matches 0.2
           return VoltageRange(self._prot.query("VOLT:RANG?"))
       ...

.. code-block:: python

   dmm.set_voltage_range("200 mV")   # VOLT:RANG 0.2
   dmm.set_voltage_range(20)         # VOLT:RANG 20
   dmm.set_voltage_range("auto")     # VOLT:RANG AUTO
   dmm.set_voltage_range(15)
   # ValueError: 15 is not a VoltageRange, use one of : 200mV, 2V, 20V, AUTO

A member accepts:

- its value out, its name and the values listed after the value out
- text without spaces, and without case when that leaves only one member: ``"2mΩ"``
  and ``"2MΩ"`` can both be members, the case then tells them apart
- numbers, and numeric text such as the replies of the device

Pass ``case_sensitive=True`` to match text only with its exact case. Two members
accepting the same value raise a ``TypeError`` as soon as the class is defined.

A member is a ``str``, its value out: ``f"{member}"`` is what the device wants, and
``member.label`` (its first accepted text) is what people read. The graphical bench
lists the labels in a drop-down.

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
