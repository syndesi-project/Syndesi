# File : demo_psu.py
# Author : Sébastien Deriaz
# License : GPL
"""
Example drivers, to try the GUI with fake_psu.py

    python examples/drivers/fake_psu.py            # a fake instrument on localhost:5025
    syndesi ui -l examples/drivers/demo_psu.py     # then stack Bench → DemoPowerSupply → IP

- DemoPowerSupply : a driver that builds its SCPI protocol itself (internal layer) and
  exposes its outputs as sub-drivers (self.channels, channel())
- Bench : a driver built on another driver
"""

from typing import Any

from syndesi import Adapter, Driver, SCPIDriver, SubDriver
from syndesi.protocols.scpi import SCPI


class PowerSupplyChannel(SubDriver):
    """
    One output of the power supply

    Parameters
    ----------
    protocol : SCPI
        Protocol of the power supply
    number : int
        Output number, starting at 1
    """

    def __init__(self, protocol: SCPI, number: int) -> None:
        self._protocol = protocol
        self.number = number

    def _select(self) -> str:
        return f"INST:NSEL {self.number};"

    def set_voltage(self, voltage: float) -> None:
        """
        Set the output voltage

        Parameters
        ----------
        voltage : float
            Volts
        """
        self._protocol.write(f"{self._select()}VOLT {voltage}")

    def get_voltage(self) -> float:
        """Voltage setpoint, in volts"""
        return float(self._protocol.query(f"{self._select()}VOLT?"))

    def measure_voltage(self) -> float:
        """Voltage measured at the output, in volts"""
        return float(self._protocol.query(f"{self._select()}MEAS:VOLT?"))

    def set_output(self, enabled: bool) -> None:
        """Enable or disable the output"""
        self._protocol.write(f"{self._select()}OUTP {'ON' if enabled else 'OFF'}")


class DemoPowerSupply(SCPIDriver):
    """
    Power supply with several outputs

    Parameters
    ----------
    adapter : Adapter
        Connection to the instrument, IP or serial
    channels : int
        Number of outputs
    """

    def __init__(self, adapter: Adapter[Any, bytes], channels: int = 2) -> None:
        super().__init__(adapter)
        self.channels = [PowerSupplyChannel(self._prot, n + 1) for n in range(channels)]

    def channel(self, number: int) -> PowerSupplyChannel:
        """
        Return one output

        Parameters
        ----------
        number : int
            Output number, starting at 1
        """
        return self.channels[number - 1]

    def open(self) -> None:
        self._prot.open()

    def close(self) -> None:
        self._prot.close()

    def test(self) -> bool:
        return "DemoPSU" in self.get_identification()


class Bench(Driver):
    """
    Test bench powering a board, a driver built on another driver

    Parameters
    ----------
    psu : DemoPowerSupply
        Power supply of the board
    rail_voltage : float
        Supply voltage of the board
    """

    def __init__(self, psu: DemoPowerSupply, rail_voltage: float = 3.3) -> None:
        super().__init__()
        self.psu = psu
        self.rail_voltage = rail_voltage

    def power_up(self) -> float:
        """Power the board and return the voltage measured"""
        rail = self.psu.channel(1)
        rail.set_voltage(self.rail_voltage)
        rail.set_output(True)
        return rail.measure_voltage()

    def power_down(self) -> None:
        """Remove the power"""
        self.psu.channel(1).set_output(False)

    def open(self) -> None:
        self.psu.open()

    def close(self) -> None:
        self.psu.close()

    def test(self) -> bool:
        return self.psu.test()
