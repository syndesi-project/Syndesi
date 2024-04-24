from ..adapters import Adapter
from .protocol import Protocol


# Raw protocols provide the user with the binary data directly,
# without converting it to string first

class Raw(Protocol):
    def __init__(self, adapter: Adapter) -> None:
        """
        Raw device, no presentation and application layers

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(adapter)

    def write(self, data : bytes):
        self._adapter.write(data)

    def query(self, data : bytes, timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        self._adapter.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    def read(self, timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        return self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

class RawStream(Protocol):
    def __init__(self, adapter: Adapter, delimiter = b'\n') -> None:
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