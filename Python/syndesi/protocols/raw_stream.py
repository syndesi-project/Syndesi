from ..adapters import IAdapter
from .iprotocol import IProtocol


# This is a temporary class to manage continuously streaming devices (Arduino for datalogging, some RS-232 multimeters, etc...)

class RawStream(IProtocol):
    def __init__(self, adapter: IAdapter, delimiter = b'\n') -> None:
        """
        Continuously streaming device with specified delimiter

        Parameters
        ----------
        adapter : IAdapter
        delimiter : bytearray
            Sample delimiter
        """
        super().__init__(adapter)

        self._buffer = b''
        self._delimiter = delimiter

    def flushRead(self):
        self._adapter.flushRead()

    def write(self, data : bytearray):
        self._adapter.write(data)

    def query(self, data : bytearray) -> bytearray:
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self, include_last=False):
        """
        Return a list of samples

        Parameters
        ----------
        include_last : bool
            Include the last sample, which is probably incomplete, False by default
        """
        self._buffer += self._adapter.read()
        samples = self._buffer.split(self._delimiter)
        if include_last:
            self._buffer = b''
            return samples
        else:
            # Put the last one back in the buffer as it probably isn't complete yet
            self._buffer = samples[-1]
            if len(samples) > 1:
                # If there's more than one sample, output all except the last one
                return samples[:-1]
            else:
                # Otherwise output nothing
                return []