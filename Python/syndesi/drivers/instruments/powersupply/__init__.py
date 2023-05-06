class IPowersupplyDC():
    # Provides power supply functions (one channel only)
    def setVoltage(self, volts : float):
        pass

    def getVoltage(self) -> float:
        pass

    def setCurrent(self, amps : float):
        pass

    def getCurrent(self) -> float:
        pass

    def setOutputState(self, state : bool):
        pass

    def measureVoltage(self) -> float:
        pass

    def measureCurrent(self) -> float:
        pass

class IMultiChannelPowersupplyDC():
    # Provides power supply functions (multi channel)
    def setVoltage(self, Channel : int, volts : float):
        pass

    def getVoltage(self, channel : int) -> float:
        pass

    def setCurrent(self, channel : int, amps : float):
        pass

    def getCurrent(self, channel : int) -> float:
        pass

    def setOutputState(self, channel : int, state : bool):
        pass

    def measureCurrent(self, channel) -> float:
        pass

    def measureVoltage(self, channel) -> float:
        pass