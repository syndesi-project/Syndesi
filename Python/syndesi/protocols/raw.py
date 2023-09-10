from ..adapters import IAdapter
from .iprotocol import IProtocol


# Raw protocols provide the user with the binary data directly,
# without converting it to string first

class Raw(IProtocol):
    def __init__(self, adapter: IAdapter) -> None:
        """
        Raw device, no presentation and application layers

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(adapter)

    def write(self, data : bytes):
        self._adapter.write(data)

    def query(self, data : bytes) -> bytes:
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self) -> bytes:
        return self._adapter.read()

class RawStream(IProtocol):
    def __init__(self, adapter: IAdapter, delimiter = b'\n') -> None:
        """
        Continuously streaming device with specified delimiter

        Parameters
        ----------
        adapter : IAdapter
        delimiter : bytes
            Sample delimiter
        """
        super().__init__(adapter)

        self._buffer = b''
        self._delimiter = delimiter

    def flushRead(self):
        self._adapter.flushRead()

    def write(self, data : bytes):
        self._adapter.write(data)

    def query(self, data : bytes) -> bytes:
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