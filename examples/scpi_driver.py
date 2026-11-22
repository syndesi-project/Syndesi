"""A driver : the instrument as a class. Start drivers/fake_psu.py first"""

from syndesi import IP, SCPIDriver


class PowerSupply(SCPIDriver):
    """A lab power supply"""

    def set_voltage(self, volts: float) -> None:
        self._prot.write(f"VOLT {volts}")

    def measure_voltage(self) -> float:
        return float(self._prot.query("MEAS:VOLT?"))

    def set_output(self, on: bool) -> None:
        self._prot.write("OUTP ON" if on else "OUTP OFF")


psu = PowerSupply(IP("127.0.0.1"))
print(psu.get_identification())  # standard SCPI commands come for free
psu.set_voltage(5)
psu.set_output(True)
print(psu.measure_voltage())  # 5.0, more or less
psu.set_output(False)
