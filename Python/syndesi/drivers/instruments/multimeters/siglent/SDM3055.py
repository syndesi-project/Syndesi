from ...instruments import Voltmeter, Ammeter
from .....wrappers.wrapper import Wrapper
from .....wrappers.ip import IP
from .....wrappers.usbvisa import USBVisa
from .....protocols.scpi import SCPI


# https://int.siglent.com/upload_file/user/SDM3055/SDM3055_RemoteManual_RC06035-E01A.pdf

class SDM3055(Voltmeter, Ammeter):
    def __init__(self, wrapper : Wrapper) -> None:
        super().__init__()

        assert isinstance(wrapper, IP) or isinstance(wrapper, USBVisa), "Invalid wrapper"
        self._prot = SCPI(wrapper)


    def measureDC(self) -> float:
        self._prot.write(b'CONF:DC')
        self._prot.write(b'INIT')
        self._prot.write(b'*TRG')
        output = float(self._prot.query(b'FETC?'))
        return output



    def measureAC(self) -> float:
        self._prot.write(b'CONF:AC')
        self._prot.write(b'INIT')
        self._prot.write(b'*TRG')
        output = float(self._prot.query(b'FETC?'))
        return output